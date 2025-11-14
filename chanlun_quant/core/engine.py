from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence

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

from typing import Tuple

from ..analysis.multilevel import MultiLevelAnalyzer, _sort_levels
from ..ai.bridge import LLMBridge
from ..ai.llm_advisor import LLMAdvisor
from ..broker.interface import BrokerInterface, SimulatedBroker
from ..core.momentum import compute_macd
from ..rsg.schema import RSG
from ..strategy.cost_pusher import CostPosition, CostPusherStrategy, TradeAction
from ..strategy.orchestrator import ChanlunOrchestrator
from ..types import Bar, PositionState, StructureState

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


class ChanlunEngine:
    """
    逐层执行引擎：
    - 输入多级 K 线，生成结构态 (`StructureState`)
    - 通过成本推进策略 (`CostPusherStrategy`) 得到交易动作
    - 可选接入 LLMAdvisor，输出 JSON 指令
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
        self.levels = tuple(cfg.levels)
        self.broker: BrokerInterface = broker or SimulatedBroker()
        self.base_position = int(base_position or cfg.max_position or 1000)

        self.cost_position = CostPosition()
        self.cost_strategy = CostPusherStrategy(base_position=self.base_position)
        self.position_state: Optional[PositionState] = None
        self.last_structure: Optional[StructureState] = None

        self.llm_bridge: Optional[LLMBridge] = None
        self.llm_advisor: Optional[LLMAdvisor] = None
        if cfg.use_llm and llm is not None and getattr(llm, "client", None):
            self.llm_bridge = LLMBridge(llm.client)
            self.llm_advisor = LLMAdvisor(bridge=self.llm_bridge, symbol=self.symbol)

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
        upper = key.upper()
        return upper

    @staticmethod
    def _bars_to_payload(bars: Sequence[Bar]) -> Dict[str, List[float]]:
        closes = [bar.close for bar in bars]
        highs = [bar.high for bar in bars]
        lows = [bar.low for bar in bars]
        if closes:
            macd = compute_macd(closes)["hist"]
        else:
            macd = []
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
    ) -> Tuple[StructureState, MultiLevelAnalyzer, Dict[str, Tuple[str, List[Bar]]]]:
        payloads, level_map = self._prepare_level_data(level_bars)
        if not payloads:
            empty = StructureState(levels=[], generated_at=None)
            analyzer = MultiLevelAnalyzer(RSG(symbol=self.symbol, levels=[]))
            return empty, analyzer, level_map

        rsg = build_multi_levels(payloads, r_seg=self.cfg.r_seg)
        rsg.symbol = self.symbol
        analyzer = MultiLevelAnalyzer(rsg)
        structure_state = analyzer.analyze(levels=list(payloads.keys()))
        self.last_structure = structure_state
        return structure_state, analyzer, level_map

    @staticmethod
    def _fusion_payload(state: StructureState) -> Dict[str, Any]:
        pairs = state.relations.get("pairs", [])
        resonance = bool(pairs) and all(pair.get("relation") == "共振" for pair in pairs if pair)
        return {
            "pairs": pairs,
            "dominant": state.relations.get("dominant"),
            "consensus_score": state.relations.get("consensus_score"),
            "resonance": resonance,
            "advice": state.advice,
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
        payload = self._bars_to_payload(bars)
        norm = self._normalize_level(level) or level
        return {
            "level": level,
            "normalized_level": norm,
            "bars": bars,
            "payload": payload,
            "fractals": [],
            "strokes": [],
            "segments": [],
            "centrals": [],
            "macd": payload.get("macd", []),
            "signals": [],
        }

    def analyze_multi_level(self, level_bars: Dict[str, List[Bar]]) -> Dict[str, Any]:
        structure_state, _, level_map = self._build_structure_state(level_bars)
        fusion = self._fusion_payload(structure_state)
        original_levels = [level_map.get(level, (level, []))[0] for level in structure_state.levels]
        structure_payload = structure_state.to_dict()
        structure_payload.setdefault("original_levels", original_levels)
        return {
            "levels": original_levels,
            "structure": structure_payload,
            "fusion": fusion,
        }

    # ---------------------------------------------------------------- execute
    def decide_and_execute(
        self, level_bars: Dict[str, List[Bar]], position: PositionState
    ) -> Dict[str, Any]:
        self.position_state = position
        if (
            self.cost_position.total_shares == 0
            and position.quantity > 0
            and position.avg_cost > 0
        ):
            self.cost_position.total_shares = position.quantity
            self.cost_position.total_spent = position.quantity * position.avg_cost
            self.cost_position.initial_capital = position.quantity * position.avg_cost
            self.cost_position.realized_profit = position.realized_profit

        structure_state, analyzer, level_map = self._build_structure_state(level_bars)
        fusion = self._fusion_payload(structure_state)
        original_levels = [level_map.get(level, (level, []))[0] for level in structure_state.levels]

        orchestrator = ChanlunOrchestrator(
            analyzer=analyzer,
            cost_strategy=self.cost_strategy,
            advisor=self.llm_advisor,
        )

        extras = {"levels": original_levels}
        last_price = self._last_price(level_map)
        result = orchestrator.plan(
            price=last_price,
            cost_position=self.cost_position,
            structure_state=structure_state,
            extras=extras,
        )

        trade_action = result.trade_action
        execution = self._apply_trade(trade_action, last_price)
        self._sync_position_state(position)

        instruction = {
            "action": trade_action.action,
            "quantity": trade_action.quantity,
            "reason": trade_action.reason,
            "source": trade_action.metadata.get("source", "strategy"),
        }
        if result.llm_decision is not None:
            instruction.update(
                {
                    "action": result.llm_decision.action,
                    "quantity": result.llm_decision.quantity,
                    "reason": result.llm_decision.reason,
                    "source": "llm",
                }
            )

        analysis_payload = {
            "levels": original_levels,
            "structure": structure_state.to_dict(),
            "fusion": fusion,
        }

        return {
            "analysis": analysis_payload,
            "ai": {
                "instruction": instruction,
                "llm_used": result.llm_decision is not None,
            },
            "execution": execution,
        }

    # ---------------------------------------------------------------- private
    def _apply_trade(self, action: TradeAction, price: float) -> Dict[str, Any]:
        if not action.requires_order():
            return {"status": "skipped"}

        qty = max(0, int(action.quantity))
        if qty == 0:
            return {"status": "skipped"}

        order_action = "buy" if action.action.startswith("BUY") else "sell"
        qty_to_use = qty
        if action.action == "SELL_ALL":
            qty_to_use = self.cost_position.total_shares
        if order_action == "sell":
            qty_to_use = min(qty_to_use, self.cost_position.total_shares)
            if qty_to_use <= 0:
                return {"status": "skipped"}

        order_info = self.broker.place_order(order_action, qty_to_use, self.symbol, price=price)

        if order_action == "buy":
            self.cost_position.buy(price, qty_to_use)
        else:
            self.cost_position.sell(price, qty_to_use)

        return {
            "status": order_info.get("status", "filled"),
            "order": order_info,
            "price": price,
            "qty": qty_to_use,
        }

    def _sync_position_state(self, position: PositionState) -> None:
        position.quantity = self.cost_position.total_shares
        position.avg_cost = self.cost_position.avg_cost
        position.realized_profit = self.cost_position.realized_profit
        if self.cost_position.initial_capital > 0:
            position.remaining_capital = max(
                0.0, self.cost_position.initial_capital - self.cost_position.realized_profit
            )
        else:
            position.remaining_capital = 0.0

        if self.cost_position.total_shares == 0:
            position.stage = "FLAT"
        elif self.cost_position.cost_zero:
            position.stage = "PROFIT_HOLD"
        else:
            position.stage = "HOLDING"