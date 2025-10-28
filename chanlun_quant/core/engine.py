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

        rsg = build_multi_levels(level_bars, r_seg=self.cfg.r_seg, cfg=self.cfg)
        seg_idx = SegmentIndex(rsg)
        levels = post_validate_levels(
            rsg,
            seg_idx,
            levels,
            candidates=["M5", "M15", "H1", "H4", "D1", "W1"],
            nest_cfg=getattr(self.cfg, "nesting", None),
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
