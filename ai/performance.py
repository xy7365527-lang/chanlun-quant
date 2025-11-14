from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional

from chanlun_quant.strategy.trade_rhythm import Action
from chanlun_quant.types import PositionState


@dataclass
class PerformanceSnapshot:
    steps: int
    trades: int
    profitable_trades: int
    losing_trades: int
    win_rate: float
    realized_profit: float
    principal_recovered: float
    remaining_capital: float
    equity: float
    max_drawdown_pct: float
    cost_stage: str
    last_action: str


class PerformanceTracker:
    """Track rolling performance statistics for prompt injection."""

    def __init__(self, *, window: int = 100) -> None:
        self.window = max(1, window)
        self.total_steps = 0
        self.total_trades = 0
        self.profitable_trades = 0
        self.losing_trades = 0
        self.last_realized_profit: Optional[float] = None
        self.equity_peak: Optional[float] = None
        self.max_drawdown_pct: float = 0.0
        self.last_action: str = "HOLD"
        self.equity_history: Deque[float] = deque(maxlen=self.window)
        self._last_snapshot: Optional[PerformanceSnapshot] = None

    def summary(self) -> Dict[str, float | int | str]:
        snapshot = self._last_snapshot or PerformanceSnapshot(
            steps=0,
            trades=0,
            profitable_trades=0,
            losing_trades=0,
            win_rate=0.0,
            realized_profit=0.0,
            principal_recovered=0.0,
            remaining_capital=0.0,
            equity=0.0,
            max_drawdown_pct=0.0,
            cost_stage="INITIAL",
            last_action="HOLD",
        )
        return {
            "steps": snapshot.steps,
            "trades": snapshot.trades,
            "profitable_trades": snapshot.profitable_trades,
            "losing_trades": snapshot.losing_trades,
            "win_rate_pct": round(snapshot.win_rate * 100, 2),
            "realized_profit": round(snapshot.realized_profit, 4),
            "principal_recovered": round(snapshot.principal_recovered, 4),
            "remaining_capital": round(snapshot.remaining_capital, 4),
            "equity": round(snapshot.equity, 4),
            "max_drawdown_pct": round(snapshot.max_drawdown_pct, 4),
            "cost_stage": snapshot.cost_stage,
            "last_action": snapshot.last_action,
        }

    def update(self, outcome_action: Action, order_executed: bool, position_state: PositionState, price: float) -> Dict[str, float | int | str]:
        self.total_steps += 1
        if order_executed:
            self.total_trades += 1

        realized_profit = float(getattr(position_state, "realized_profit", 0.0) or 0.0)
        if self.last_realized_profit is None:
            self.last_realized_profit = realized_profit

        delta_realized = realized_profit - self.last_realized_profit
        if order_executed and abs(delta_realized) > 1e-9:
            if delta_realized > 0:
                self.profitable_trades += 1
            elif delta_realized < 0:
                self.losing_trades += 1

        self.last_realized_profit = realized_profit
        self.last_action = outcome_action.value if isinstance(outcome_action, Action) else str(outcome_action)

        quantity = float(getattr(position_state, "quantity", 0.0) or 0.0)
        remaining_capital = float(getattr(position_state, "remaining_capital", 0.0) or 0.0)
        reference_price = price if price > 0 else float(getattr(position_state, "avg_cost", 0.0) or 0.0)
        equity = remaining_capital + quantity * reference_price

        self.equity_history.append(equity)
        if self.equity_peak is None or equity > self.equity_peak:
            self.equity_peak = equity
        if self.equity_peak and self.equity_peak > 0:
            drawdown = (self.equity_peak - equity) / self.equity_peak
            self.max_drawdown_pct = max(self.max_drawdown_pct, drawdown * 100)

        total_closed = self.profitable_trades + self.losing_trades
        win_rate = self.profitable_trades / total_closed if total_closed else 0.0

        snapshot = PerformanceSnapshot(
            steps=self.total_steps,
            trades=self.total_trades,
            profitable_trades=self.profitable_trades,
            losing_trades=self.losing_trades,
            win_rate=win_rate,
            realized_profit=realized_profit,
            principal_recovered=float(getattr(position_state, "principal_recovered", 0.0) or 0.0),
            remaining_capital=remaining_capital,
            equity=equity,
            max_drawdown_pct=self.max_drawdown_pct,
            cost_stage=str(getattr(position_state, "cost_stage", "INITIAL") or "INITIAL"),
            last_action=self.last_action,
        )
        self._last_snapshot = snapshot
        return self.summary()

