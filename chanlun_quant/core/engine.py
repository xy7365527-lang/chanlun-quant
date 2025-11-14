from __future__ import annotations

import time
from dataclasses import asdict, fields
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..ai.interface import ChanLLM
from ..agents.orchestrator import run_agents
from ..config import Config
from ..core.backtest import BacktestBroker
from ..core.broker import Broker
from ..core.trace import TraceLog
from ..core.risk import RiskEngine, RiskLimits
from ..core.envelope import envelope_from_trend
from ..features.segment_index import SegmentIndex
from ..fugue.level_coordinator import fuse_to_net_orders, sanitize_and_clip
from ..ledger.book import Ledger, apply_fill_to_bucket, eod_flat_pen
from ..rsg.build import build_multi_levels
from ..selector.level_selector import post_validate_levels, select_levels
from ..strategy.cost_zero_baseline import CostZeroBaseline
from ..strategy.cutter import signals_to_plan

DEFAULT_CANDIDATES: List[str] = ["M5", "M15", "H1", "D1", "W1"]


def _ensure_bars_payload(level: str, payload: Dict[str, Iterable[float]]) -> Dict[str, List[float]]:
    required = ("close", "high", "low", "macd")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"datafeed.get_bars 缺少字段 {missing} (level={level})")
    return {key: list(payload[key]) for key in required}


def _ensure_ledger(obj: Any) -> Ledger:
    if isinstance(obj, Ledger):
        return obj
    led = Ledger()
    if isinstance(obj, dict):
        led.core_qty = float(obj.get("core_qty", 0.0))
        led.core_avg_cost = float(obj.get("core_avg_cost", 0.0))
        led.remaining_cost = float(obj.get("remaining_cost", 0.0))
        led.free_ride_qty = float(obj.get("free_ride_qty", 0.0))
        pen = obj.get("pen", {})
        if isinstance(pen, dict):
            led.pen.qty = float(pen.get("qty", 0.0))
            led.pen.avg_cost = float(pen.get("avg_cost", 0.0))
        segment = obj.get("segment", {})
        if isinstance(segment, dict):
            led.segment.qty = float(segment.get("qty", 0.0))
            led.segment.avg_cost = float(segment.get("avg_cost", 0.0))
    return led


class Engine:
    """成本归零·多重赋格 主流程引擎。"""

    def __init__(
        self,
        cfg: Config,
        broker: Broker | BacktestBroker | None = None,
        baseline: Optional[CostZeroBaseline] = None,
        llm_client: Optional[Any] = None,
        llm: Optional[ChanLLM] = None,
    ) -> None:
        self.cfg = cfg
        self.broker = broker or Broker()
        self.baseline = baseline or CostZeroBaseline()
        self.llm = llm or ChanLLM(client=llm_client)
        self.last_plan: List[Dict[str, Any]] = []
        self.last_fills: List[Dict[str, Any]] = []
        self.trace = TraceLog() if getattr(self.cfg, "enable_trace", False) else None
        self.risk = RiskEngine(
            RiskLimits(
                max_daily_loss=self.cfg.daily_loss_limit,
                max_child_ratio=self.cfg.risk_child_ratio,
                max_orders_per_cycle=self.cfg.max_orders_per_cycle,
                max_orders_per_min=self.cfg.max_orders_per_min,
                kill_switch=self.cfg.kill_switch,
            )
        )

    def _select_levels(self, symbol: str, datafeed: Any, candidates: Sequence[str]) -> List[str]:
        if self.cfg.use_auto_levels:
            atr_fetcher = getattr(datafeed, "get_atr", lambda *_: 0.0)
            return select_levels(symbol, atr_fetcher, candidates)
        return ["M15", "H1", "D1"]

    def run_cycle(
        self,
        symbol: str,
        datafeed: Any,
        last_price: float,
        ledger: Ledger | Dict[str, Any],
        eod: bool = False,
    ) -> List[Dict[str, Any]]:
        ledger_obj = _ensure_ledger(ledger)

        candidates = list(getattr(self.cfg, "level_candidates", DEFAULT_CANDIDATES))
        levels = self._select_levels(symbol, datafeed, candidates)

        level_bars: Dict[str, Dict[str, List[float]]] = {}
        for level in levels:
            payload = datafeed.get_bars(symbol, level)
            level_bars[level] = _ensure_bars_payload(level, payload)

        rsg = build_multi_levels(level_bars, r_seg=self.cfg.r_seg)
        seg_idx = SegmentIndex(rsg)
        rsg.build_info["segments"] = len(seg_idx.rsg.segments)
        rsg.build_info["pens"] = len(seg_idx.rsg.pens)
        levels = post_validate_levels(
            rsg,
            seg_idx,
            levels,
            candidates=["M5", "M15", "H1", "H4", "D1", "W1"],
            nest_cfg=self.cfg.nesting_cfg,
        )

        envelope = envelope_from_trend(seg_idx, position_state=None, cfg=self.cfg)

        setattr(ledger_obj, "latest_price", last_price)
        signals, env_suggestions = run_agents(levels, seg_idx, last_price)
        pre_signals = [
            {
                "level": sig.level,
                "kind": sig.kind,
                "refs": sig.refs,
                "methods": sig.methods,
                "weight": sig.weight,
                "why": sig.why,
            }
            for sig in signals
        ]
        setattr(ledger_obj, "_pre_signals", pre_signals)
        if self.trace:
            self.trace.write(
                {
                    "phase": "pre_guard",
                    "levels": levels,
                    "selector_reason": rsg.build_info.get("level_selector_reason", ""),
                    "pre_signals": pre_signals,
                    "envelope": getattr(envelope, "__dict__", str(envelope)),
                }
            )
        plan = signals_to_plan(
            signals,
            core_qty=ledger_obj.core_qty,
            child_max_ratio=envelope.child_max_ratio,
        )

        if env_suggestions and plan.envelope_update is None:
            plan.envelope_update = env_suggestions[-1]

        if self.cfg.use_cost_zero_ai:
            try:
                ledger_payload = asdict(ledger_obj)
                if pre_signals:
                    ledger_payload["_pre_signals"] = pre_signals
                llm_plan = self.llm.decide_costzero(seg_idx, ledger_payload, envelope, self.cfg)
                if llm_plan.proposals:
                    plan.proposals.extend(llm_plan.proposals)
                if llm_plan.envelope_update:
                    plan.envelope_update = plan.envelope_update or llm_plan.envelope_update
            except RuntimeError:
                pass
        else:
            baseline_plan = self.baseline.propose(seg_idx, last_price)
            plan.proposals.extend(baseline_plan.proposals)

        risk_ctx: Dict[str, Any] = {
            "core_qty": ledger_obj.core_qty,
            "guard_strict": getattr(self.cfg, "guard_strict", False),
            "bucket_capacity": {"pen": max(0.0, ledger_obj.pen.qty), "segment": max(0.0, ledger_obj.segment.qty)},
            "min_step_abs": 0.0,
            "k_grid": getattr(self.cfg, "k_grid", 0.25),
            "fee_bps": getattr(self.cfg, "fee_bps", 4.0),
            "slippage_bps": getattr(self.cfg, "slippage_bps", 3.0),
        }

        safe_plan = sanitize_and_clip(plan, envelope, seg_idx, risk_ctx=risk_ctx)
        base_orders = fuse_to_net_orders(safe_plan)
        if not base_orders:
            orders: List[Dict[str, Any]] = []
            if self.trace:
                self.trace.write({
                    "phase": "post_guard",
                    "plan": [p.__dict__ for p in safe_plan.proposals],
                    "orders": orders,
                })
        else:
            if self.risk.should_block(
                core_qty=ledger_obj.core_qty,
                envelope_child_ratio=envelope.child_max_ratio,
                proposals=base_orders,
            ):
                if self.trace:
                    self.trace.write({
                        "phase": "risk_block",
                        "reason": self.risk.state.blocked_reason,
                        "orders": base_orders,
                    })
                return []

            plan_id = self.risk.idempotency_key(symbol, base_orders)
            orders = fuse_to_net_orders(safe_plan, plan_id=plan_id)
            plan_ts = int(time.time() * 1000)
            for order in orders:
                order["plan_ts"] = plan_ts

            if self.trace:
                self.trace.write({
                    "phase": "post_guard",
                    "plan": [p.__dict__ for p in safe_plan.proposals],
                    "orders": orders,
                    "idem_key": plan_id,
                })

        fills: List[Dict[str, Any]] = []
        if orders and self.trace:
            self.trace.write({"phase": "pre_exec", "orders": orders})
        if orders:
            if isinstance(self.broker, BacktestBroker):
                fills = self.broker.execute(symbol, orders, last_price=last_price)
            else:
                fills = self.broker.execute(symbol, orders)
            for fill in fills:
                price = fill.get("price", last_price)
                apply_fill_to_bucket(
                    ledger_obj,
                    bucket=fill["bucket"],
                    side=fill["side"],
                    fill_qty=float(fill["qty"]),
                    fill_price=price if price is not None else last_price,
                )
                realized = float(fill.get("realized", 0.0))
                self.risk.on_fill_pnl(realized)

        if orders:
            self.risk.on_orders_sent(orders)

        if eod:
            eod_orders = eod_flat_pen(ledger_obj)
            if eod_orders:
                if isinstance(self.broker, BacktestBroker):
                    eod_fills = self.broker.execute(symbol, eod_orders, last_price=last_price)
                else:
                    eod_fills = self.broker.execute(symbol, eod_orders)
                for fill in eod_fills:
                    price = fill.get("price", last_price)
                    apply_fill_to_bucket(
                        ledger_obj,
                        bucket=fill["bucket"],
                        side=fill["side"],
                        fill_qty=float(fill["qty"]),
                        fill_price=price if price is not None else last_price,
                    )
                orders.extend(eod_orders)
                fills.extend(eod_fills)

        if self.trace:
            self.trace.write({
                "phase": "post_exec",
                "fills": fills,
                "ledger": {
                    "remaining_cost": ledger_obj.remaining_cost,
                    "stage": ledger_obj.stage,
                    "free_ride_qty": ledger_obj.free_ride_qty,
                    "realized_total": ledger_obj.realized_total,
                    "pen": ledger_obj.pen.__dict__,
                    "segment": ledger_obj.segment.__dict__,
                },
            })

        self.last_plan = [
            {
                "bucket": p.bucket,
                "action": p.action,
                "size_delta": p.size_delta,
                "why": p.why,
                "refs": p.refs,
                "methods": getattr(p, "methods", None),
                "price_band": p.price_band,
            }
            for p in safe_plan.proposals
        ]
        self.last_fills = fills

        return orders


# ---------------------------------------------------------------------------
# 新一代分层执行引擎：多级结构 → 策略节奏 → LLM → 执行
# ---------------------------------------------------------------------------

from ..analysis.structure import StructureAnalyzer
from ..broker.interface import BrokerInterface, OrderResult, SimulatedBroker
from ..core.momentum import compute_macd
from ..strategy.trade_rhythm import Action, TradeRhythmEngine
from ..types import Bar, PositionState, StructureLevelState, StructureState

LEVEL_ALIASES: Dict[str, str] = {
    "1m": "M1",
    "m1": "M1",
    "5m": "M5",
    "m5": "M5",
    "15m": "M15",
    "m15": "M15",
    "30m": "M30",
    "m30": "M30",
    "1h": "H1",
    "60m": "H1",
    "h1": "H1",
    "4h": "H4",
    "h4": "H4",
    "1d": "D1",
    "d1": "D1",
    "1w": "W1",
    "w1": "W1",
}

_LEVEL_ORDER: Dict[str, int] = {
    "M1": 0,
    "M5": 1,
    "M15": 2,
    "M30": 3,
    "H1": 4,
    "H4": 5,
    "D1": 6,
    "W1": 7,
}


def _sort_levels(levels: Iterable[str]) -> List[str]:
    unique: List[str] = []
    for level in levels:
        if not level:
            continue
        upper = level.upper()
        if upper not in unique:
            unique.append(upper)
    return sorted(unique, key=lambda lv: (_LEVEL_ORDER.get(lv, len(_LEVEL_ORDER)), lv))


class ChanlunEngine:
    """
    逐层执行引擎：
    - 输入多级 K 线，生成结构态 (`StructureState`)
    - 利用交易节奏引擎 (`TradeRhythmEngine`) 得到动作建议
    - 可选接入 ChanLLM，输出 JSON 指令
    - 调用 BrokerInterface 执行下单
    """

    def __init__(
        self,
        cfg: Config,
        llm: Optional[ChanLLM] = None,
        broker: Optional[BrokerInterface] = None,
        base_position: Optional[int] = None,
    ) -> None:
        self.cfg = cfg
        self.symbol = cfg.symbol
        normalized_levels: List[str] = []
        for lvl in cfg.levels:
            norm = self._normalize_level(lvl)
            if norm:
                normalized_levels.append(norm)
        if not normalized_levels:
            normalized_levels = ["M15", "H1", "D1"]
        self.levels = tuple(_sort_levels(normalized_levels))
        if tuple(cfg.levels) != self.levels:
            self.cfg.levels = self.levels
        self.broker: BrokerInterface = broker or SimulatedBroker()
        self.base_position = int(base_position or cfg.max_position or 1000)
        self.llm = llm

        self.trade_engine = TradeRhythmEngine(
            initial_capital=float(cfg.initial_capital or 0.0),
            initial_quantity=float(cfg.initial_buy_quantity or 0.0),
        )
        self.holding_manager = self.trade_engine.get_holding_manager()
        self.position_state: PositionState = self.holding_manager.get_position_state()
        self.last_structure: Optional[StructureState] = None
        self.last_extras: Dict[str, Any] = {}
        self.last_instruction: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _normalize_level(level: str) -> Optional[str]:
        if not level:
            return None
        key = level.strip()
        if not key:
            return None
        alias = LEVEL_ALIASES.get(key.lower())
        if alias:
            return alias
        return key.upper()

    @staticmethod
    def _bars_to_payload(bars: Sequence[Bar]) -> Dict[str, List[float]]:
        closes = [bar.close for bar in bars]
        highs = [bar.high for bar in bars]
        lows = [bar.low for bar in bars]
        macd = compute_macd(closes)["hist"] if closes else []
        return {"close": closes, "high": highs, "low": lows, "macd": macd}

    def _prepare_level_data(
        self, level_bars: Dict[str, List[Bar]]
    ) -> Tuple[Dict[str, Dict[str, List[float]]], Dict[str, Tuple[str, List[Bar]]]]:
        payloads: Dict[str, Dict[str, List[float]]] = {}
        level_map: Dict[str, Tuple[str, List[Bar]]] = {}
        for level, bars in level_bars.items():
            norm = self._normalize_level(level)
            if norm is None or not bars:
                continue
            payloads[norm] = self._bars_to_payload(bars)
            level_map[norm] = (level, bars)
        return payloads, level_map

    def _build_structure_state(
        self, level_bars: Dict[str, List[Bar]]
    ) -> Tuple[StructureState, StructureAnalyzer, Dict[str, Tuple[str, List[Bar]]]]:
        payloads, level_map = self._prepare_level_data(level_bars)
        levels = _sort_levels(payloads.keys())
        if not levels:
            analyzer = StructureAnalyzer([], config=self.cfg)
            empty = StructureState(levels=[])
            self.last_structure = empty
            self.last_extras = {}
            return empty, analyzer, level_map

        bars_by_level: Dict[str, List[Bar]] = {
            level: list(level_map.get(level, (level, []))[1]) for level in levels if level in level_map
        }
        analyzer = StructureAnalyzer(levels, config=self.cfg)
        structure_state, extras = analyzer.analyze(bars_by_level, previous=self.last_structure)
        structure_state.metadata.setdefault("analysis_extras", extras)
        matrix = structure_state.relation_matrix or {}
        structure_state.relations.setdefault("pairs", matrix.get("matrix", []))
        structure_state.relations.setdefault("dominant", matrix.get("dominant_direction"))
        structure_state.relations.setdefault("consensus_score", matrix.get("score"))
        structure_state.metadata.setdefault("fusion_summary", matrix.get("summary"))
        self.last_structure = structure_state
        self.last_extras = extras
        return structure_state, analyzer, level_map

    @staticmethod
    def _fusion_payload(state: StructureState) -> Dict[str, Any]:
        matrix = state.relation_matrix or {}
        pairs_raw = state.relations.get("pairs") or matrix.get("matrix") or []
        pairs: List[Dict[str, Any]] = []
        for item in pairs_raw:
            if isinstance(item, dict):
                pairs.append(
                    {
                        "higher": item.get("higher"),
                        "lower": item.get("lower"),
                        "relation": item.get("relation"),
                    }
                )
        resonance = bool(matrix.get("resonance"))
        return {
            "pairs": pairs,
            "dominant": matrix.get("dominant_direction") or state.relations.get("dominant"),
            "consensus_score": matrix.get("score") or state.relations.get("consensus_score"),
            "resonance": resonance,
            "advice": matrix.get("summary") or state.metadata.get("fusion_summary"),
        }

    @staticmethod
    def _last_price(level_map: Dict[str, Tuple[str, List[Bar]]]) -> float:
        if not level_map:
            return 0.0
        ordered = _sort_levels(level_map.keys())
        driver = ordered[0]
        bars = level_map[driver][1]
        return bars[-1].close if bars else 0.0

    # ---------------------------------------------------------------- analysis
    def analyze_one_level(self, bars: List[Bar], level: str) -> Dict[str, Any]:
        bars_copy = list(bars)
        payload = self._bars_to_payload(bars_copy)
        norm = self._normalize_level(level) or level
        analyzer = StructureAnalyzer([norm], config=self.cfg)
        structure, _ = analyzer.analyze({norm: bars_copy})
        state = structure.level_states.get(norm, StructureLevelState(level=norm))
        return {
            "level": level,
            "normalized_level": norm,
            "bars": bars_copy,
            "payload": payload,
            "fractals": state.metadata.get("fractals", []),
            "strokes": list(state.strokes.values()),
            "segments": list(state.segments.values()),
            "centrals": [],
            "macd": payload.get("macd", []),
            "signals": list(state.signals),
        }

    def analyze_multi_level(self, level_bars: Dict[str, List[Bar]]) -> Dict[str, Any]:
        structure_state, _, level_map = self._build_structure_state(level_bars)
        fusion = self._fusion_payload(structure_state)
        original_levels = [level_map.get(level, (level, []))[0] for level in structure_state.levels]
        return {
            "levels": original_levels,
            "structure": structure_state,
            "fusion": fusion,
            "extras": dict(self.last_extras),
        }

    # ---------------------------------------------------------------- execute
    def decide_and_execute(
        self, level_bars: Dict[str, List[Bar]], position: PositionState
    ) -> Dict[str, Any]:
        structure_state, _, level_map = self._build_structure_state(level_bars)
        fusion = self._fusion_payload(structure_state)
        original_levels = [level_map.get(level, (level, []))[0] for level in structure_state.levels]
        last_price = self._last_price(level_map)
        signal = str(self.last_extras.get("signal", "HOLD") or "HOLD").upper()
        action_plan = self.trade_engine.on_signal(signal, last_price, self.cfg)
        order_result, _ = self._execute_action_plan(action_plan, last_price)
        llm_instruction = self._maybe_run_llm(structure_state, fusion, last_price)
        instruction = llm_instruction or self._make_instruction(action_plan, source="strategy")
        self.last_instruction = instruction
        self._update_external_position(position)
        execution = self._make_execution_payload(order_result, last_price, action_plan, signal)
        analysis_payload = {
            "levels": original_levels,
            "structure": structure_state,
            "fusion": fusion,
            "extras": dict(self.last_extras),
        }
        ai_payload = {
            "instruction": instruction,
            "llm_used": bool(llm_instruction),
        }
        if llm_instruction:
            ai_payload["llm_instruction"] = llm_instruction
        return {
            "analysis": analysis_payload,
            "ai": ai_payload,
            "execution": execution,
        }

    # ---------------------------------------------------------------- private helpers
    def _execute_action_plan(self, plan: Dict[str, Any], price: float) -> Tuple[Optional[OrderResult], float]:
        action_value = plan.get("action")
        if isinstance(action_value, Action):
            action = action_value
        elif isinstance(action_value, str):
            try:
                action = Action(action_value)
            except ValueError:
                action = Action.HOLD
        else:
            action = Action.HOLD

        quantity = float(plan.get("quantity", 0.0) or 0.0)

        if action == Action.WITHDRAW_CAPITAL:
            self.holding_manager.withdraw_capital()
            return None, 0.0

        if quantity <= 0:
            return None, 0.0

        if action == Action.BUY_INITIAL:
            order = self.broker.place_order("buy", quantity, self.symbol, price=price)
            self.holding_manager.buy(price, quantity, is_initial_buy=True)
            return order, quantity

        if action == Action.BUY_REFILL:
            order = self.broker.place_order("buy", quantity, self.symbol, price=price)
            self.holding_manager.buy(price, quantity, is_initial_buy=False)
            return order, quantity

        if action in {Action.SELL_PARTIAL, Action.SELL_ALL}:
            order = self.broker.place_order("sell", quantity, self.symbol, price=price)
            self.holding_manager.sell(price, quantity)
            return order, quantity

        return None, 0.0

    def _make_instruction(self, plan: Dict[str, Any], *, source: str) -> Dict[str, Any]:
        data = self._action_plan_to_dict(plan)
        return {
            "action": data.get("action", "HOLD"),
            "quantity": float(data.get("quantity", 0.0) or 0.0),
            "reason": data.get("reason", ""),
            "source": source,
            "stage": data.get("stage"),
            "next_stage": data.get("next_stage"),
            "cost_stage": data.get("cost_stage"),
            "allowed_actions": data.get("allowed_actions"),
        }

    def _action_plan_to_dict(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        plain: Dict[str, Any] = {}
        for key, value in plan.items():
            if isinstance(value, Action):
                plain[key] = value.value
            elif isinstance(value, set):
                plain[key] = [
                    item.value if isinstance(item, Action) else item for item in value
                ]
            else:
                plain[key] = value
        return plain

    def _make_execution_payload(
        self,
        order: Optional[OrderResult],
        price: float,
        plan: Dict[str, Any],
        signal: str,
    ) -> Dict[str, Any]:
        status = "skipped"
        order_dict = None
        if isinstance(order, OrderResult):
            status = order.status
            order_dict = {
                "action": order.action,
                "quantity": order.quantity,
                "price": order.price,
                "status": order.status,
            }
        return {
            "status": status,
            "order": order_dict,
            "price": price,
            "signal": signal,
            "position": {
                "quantity": self.position_state.quantity,
                "avg_cost": self.position_state.avg_cost,
                "stage": self.position_state.stage,
                "cost_stage": self.position_state.cost_stage,
            },
            "action_plan": self._action_plan_to_dict(plan),
        }

    def _update_external_position(self, external: PositionState) -> None:
        current = self.holding_manager.get_position_state()
        self.position_state = current
        for field in fields(PositionState):
            setattr(external, field.name, getattr(current, field.name))

    def _maybe_run_llm(
        self,
        structure: StructureState,
        fusion: Dict[str, Any],
        price: float,
    ) -> Optional[Dict[str, Any]]:
        if not (self.cfg.use_llm and self.llm and getattr(self.llm, "structure_llm", None)):
            return None
        context = {
            "symbol": self.symbol,
            "price_hint": price,
            "fusion": fusion,
            "levels": list(structure.levels),
            "position": asdict(self.position_state),
            "analysis_extras": dict(self.last_extras),
        }
        try:
            decision = self.llm.decide_action(context)
        except Exception:
            return None
        return {
            "action": decision.action,
            "quantity": decision.quantity,
            "reason": decision.reason,
            "confidence": decision.confidence,
            "price_hint": decision.price_hint,
            "source": "llm",
        }