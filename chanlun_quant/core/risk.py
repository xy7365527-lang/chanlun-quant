from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class RiskLimits:
    max_daily_loss: float = 0.0
    max_child_ratio: float = 0.40
    max_orders_per_cycle: int = 4
    max_orders_per_min: int = 12
    kill_switch: bool = False


@dataclass
class RiskState:
    pnl_today: float = 0.0
    order_count_minute: int = 0
    last_minute_ts: int = 0
    last_plan_hash: str = ""
    last_plan_id: str = ""
    blocked_reason: str = ""


class RiskEngine:
    """风控引擎：日内亏损 / 敞口 / 频次限制 + 幂等控制。"""

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()
        self.state = RiskState()

    def _hash_plan(self, proposals: List[Dict[str, Any]]) -> str:
        sig = "|".join(
            f"{p.get('bucket')}/{p.get('action')}/{p.get('qty') or p.get('size_delta')}/{p.get('price_band')}/{p.get('refs')}"
            for p in proposals
        )
        return hashlib.sha256(sig.encode("utf-8")).hexdigest()

    def idempotency_key(self, symbol: str, proposals: List[Dict[str, Any]]) -> str:
        plan_hash = self._hash_plan(proposals)
        ts = int(time.time() * 1000)
        return f"{symbol}:{ts}:{plan_hash[:12]}"

    def _tick_minute(self) -> None:
        now_minute = int(time.time() // 60)
        if now_minute != self.state.last_minute_ts:
            self.state.last_minute_ts = now_minute
            self.state.order_count_minute = 0

    def should_block(
        self,
        core_qty: float,
        envelope_child_ratio: float,
        proposals: List[Dict[str, Any]],
    ) -> bool:
        limits = self.limits
        state = self.state
        self._tick_minute()

        if limits.kill_switch:
            state.blocked_reason = "kill_switch"
            return True

        if limits.max_daily_loss < 0 and state.pnl_today <= limits.max_daily_loss:
            state.blocked_reason = "daily_loss_limit"
            return True

        if envelope_child_ratio > limits.max_child_ratio:
            state.blocked_reason = "child_ratio_exceed"
            return True

        if len(proposals) > limits.max_orders_per_cycle:
            state.blocked_reason = "too_many_orders_in_cycle"
            return True

        if state.order_count_minute + len(proposals) > limits.max_orders_per_min:
            state.blocked_reason = "too_many_orders_per_min"
            return True

        plan_hash = self._hash_plan(proposals)
        if plan_hash and plan_hash == state.last_plan_hash:
            state.blocked_reason = "idempotent_same_plan"
            return True

        state.blocked_reason = ""
        return False

    def on_orders_sent(self, proposals: List[Dict[str, Any]]) -> None:
        self._tick_minute()
        self.state.order_count_minute += len(proposals)
        self.state.last_plan_hash = self._hash_plan(proposals)

    def on_fill_pnl(self, realized_pnl: float) -> None:
        self.state.pnl_today += realized_pnl

