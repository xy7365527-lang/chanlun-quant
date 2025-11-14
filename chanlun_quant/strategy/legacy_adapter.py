from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

try:
    from chanlun.backtesting.base import MarketDatas, Operation, POSITION, Strategy
except ImportError:  # pragma: no cover - legacy modules are always present in production
    MarketDatas = Any  # type: ignore
    Operation = Any  # type: ignore
    POSITION = Any  # type: ignore
    Strategy = Any  # type: ignore

from chanlun_quant.strategy.trade_rhythm import Action

PriceResolver = Callable[[str, MarketDatas, Optional[Operation]], float]


def _default_price(symbol: str, market_data: MarketDatas, op: Optional[Operation]) -> float:
    """Return the latest close price for *symbol* from a legacy MarketDatas provider."""
    if not hasattr(market_data, "frequencys"):
        raise ValueError("market_data must expose 'frequencys' for default price resolver")
    frequencies: Sequence[str] = getattr(market_data, "frequencys")
    if not frequencies:
        raise ValueError("market_data.frequencys must contain at least one frequency")
    primary_freq = frequencies[0]
    frame = market_data.klines(symbol, primary_freq)
    if frame is None or len(frame) == 0:
        raise ValueError(f"klines returned no data for symbol={symbol}, freq={primary_freq}")
    if hasattr(frame, "iloc"):
        last_row = frame.iloc[-1]
        if "close" in last_row:
            return float(last_row["close"])
        if "c" in last_row:
            return float(last_row["c"])
    # pandas not available or atypical payload: fall back to dict/list access
    last_row = frame[-1]
    if isinstance(last_row, dict):
        if "close" in last_row:
            return float(last_row["close"])
        if "c" in last_row:
            return float(last_row["c"])
    raise ValueError(f"Unable to infer price from klines payload for symbol={symbol}")


@dataclass
class LegacySignal:
    """Normalized signal emitted by the legacy adapter."""

    signal: str
    price: float
    operation: Operation
    suggested_action: Action
    reason: str
    pos_rate: float


class LegacyPositionBook:
    """Very small POSITION proxy that keeps the legacy strategy state in sync with TradeRhythmEngine."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self._position: Optional[POSITION] = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def snapshot(self) -> Dict[str, POSITION]:
        if self._position and getattr(self._position, "amount", 0) > 0:
            key = getattr(self._position, "open_uid", f"{self.symbol}:legacy")
            return {key: self._position}
        return {}

    def reset(self) -> None:
        self._position = None

    def apply_fill(
        self,
        action: Action,
        quantity: float,
        price: float,
        op: Optional[Operation],
    ) -> None:
        if quantity <= 0:
            return
        if action in (Action.BUY_INITIAL, Action.BUY_REFILL):
            self._apply_buy(quantity, price, op)
        elif action in (Action.SELL_PARTIAL, Action.SELL_ALL):
            self._apply_sell(quantity, price, op)
        # WITHDRAW_CAPITAL / HOLD 不影响 legacy POSITION

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _apply_buy(self, quantity: float, price: float, op: Optional[Operation]) -> None:
        now = datetime.now(timezone.utc)
        if self._position is None or getattr(self._position, "amount", 0) <= 0:
            mmd = getattr(op, "mmd", "legacy")
            uid = getattr(op, "open_uid", f"{self.symbol}:{mmd}")
            loss_price = getattr(op, "loss_price", None)
            msg = getattr(op, "msg", "")
            info = getattr(op, "info", {}) or {}
            self._position = POSITION(
                code=self.symbol,
                mmd=mmd,
                balance=quantity * price,
                price=price,
                amount=quantity,
                loss_price=loss_price,
                open_datetime=now,
                open_msg=msg,
                info=info,
                open_uid=uid,
            )
            self._position.now_pos_rate = getattr(op, "pos_rate", 1.0)
        else:
            pos = self._position
            prev_amount = getattr(pos, "amount", 0.0)
            total_amount = prev_amount + quantity
            if total_amount <= 0:
                return
            prev_cost = getattr(pos, "price", 0.0) * prev_amount
            new_cost = price * quantity
            pos.price = (prev_cost + new_cost) / total_amount
            pos.amount = total_amount
            pos.balance = getattr(pos, "balance", 0.0) + new_cost
            if op is not None:
                pos.loss_price = getattr(op, "loss_price", pos.loss_price)
                pos.open_msg = getattr(op, "msg", pos.open_msg)
                pos.info = getattr(op, "info", pos.info)
                pos.now_pos_rate = getattr(op, "pos_rate", pos.now_pos_rate)

    def _apply_sell(self, quantity: float, price: float, op: Optional[Operation]) -> None:
        if self._position is None or getattr(self._position, "amount", 0) <= 0:
            return
        pos = self._position
        prev_amount = float(getattr(pos, "amount", 0.0))
        sell_amount = min(prev_amount, quantity)
        pos.amount = max(prev_amount - sell_amount, 0.0)
        pos.release_balance = getattr(pos, "release_balance", 0.0) + sell_amount * price
        cost_price = getattr(pos, "price", 0.0)
        if cost_price > 0:
            realized = (price - cost_price) * sell_amount
            pos.profit = getattr(pos, "profit", 0.0) + realized
            pos.profit_rate = realized / (cost_price * sell_amount) if sell_amount > 0 else 0.0
        if pos.amount <= 0:
            pos.close_datetime = datetime.now(timezone.utc)
            pos.close_msg = getattr(op, "msg", getattr(pos, "close_msg", ""))
            pos.open_keys = {}
            pos.close_keys = {}


class LegacyStrategyAdapter:
    """
    Convert legacy Strategy.open/close outputs to TradeRhythmEngine-friendly signals.

    Usage (simplified):

    >>> adapter = LegacyStrategyAdapter(symbol, legacy_strategy)
    >>> signal = adapter.step(market_data_provider)
    >>> if signal:
    ...     action_plan = trade_engine.on_signal(signal.signal, signal.price, cfg)
    ...     adapter.register_fill(action_plan["action"], action_plan["quantity"], signal.price, signal)
    """

    def __init__(
        self,
        symbol: str,
        strategy: Strategy,
        *,
        price_resolver: PriceResolver = _default_price,
    ) -> None:
        self.symbol = symbol
        self.strategy = strategy
        self.price_resolver = price_resolver
        self.position_book = LegacyPositionBook(symbol)
        self._last_signal: Optional[LegacySignal] = None

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.position_book.reset()
        if hasattr(self.strategy, "clear"):
            self.strategy.clear()
        self._last_signal = None

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------
    def step(self, market_data: MarketDatas) -> Optional[LegacySignal]:
        positions = self.position_book.snapshot()
        open_ops = self._normalize(self.strategy.open(self.symbol, market_data, positions))
        open_ops = self._filter(open_ops)
        if open_ops:
            op = self._select(open_ops, prefer_sell=False)
            if op:
                price = self.price_resolver(self.symbol, market_data, op)
                self._last_signal = self._to_signal(op, price)
                return self._last_signal

        for pos in positions.values():
            close_ops_raw = self.strategy.close(self.symbol, pos.mmd, pos, market_data)
            close_ops = self._normalize(close_ops_raw)
            close_ops = self._filter(close_ops, is_close=True)
            if not close_ops:
                continue
            op = self._select(close_ops, prefer_sell=True)
            if op:
                price = self.price_resolver(self.symbol, market_data, op)
                self._last_signal = self._to_signal(op, price)
                return self._last_signal

        self._last_signal = None
        return None

    # ------------------------------------------------------------------
    # Synchronisation with executed trades
    # ------------------------------------------------------------------
    def register_fill(
        self,
        action: Action,
        quantity: float,
        price: float,
        signal: Optional[LegacySignal] = None,
    ) -> None:
        effective_signal = signal or self._last_signal
        op = effective_signal.operation if effective_signal else None
        self.position_book.apply_fill(action, quantity, price, op)

    def positions(self) -> Dict[str, POSITION]:
        return self.position_book.snapshot()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(
        operations: Optional[Iterable[Operation] | Operation],
    ) -> List[Operation]:
        if operations is None:
            return []
        if isinstance(operations, Operation):
            return [operations]
        return [op for op in operations if op is not None]

    def _filter(self, operations: List[Operation], *, is_close: bool = False) -> List[Operation]:
        if not operations:
            return []
        if not is_close and getattr(self.strategy, "is_filter_opts", None):
            try:
                if self.strategy.is_filter_opts():
                    operations = self.strategy.filter_opts(operations)  # type: ignore[arg-type]
            except Exception:
                pass
        return operations

    @staticmethod
    def _select(operations: List[Operation], *, prefer_sell: bool) -> Optional[Operation]:
        if not operations:
            return None
        ranked = sorted(
            operations,
            key=lambda op: (
                0 if (prefer_sell and getattr(op, "opt", "") == "sell") else 1,
                -float(getattr(op, "pos_rate", 0.0)),
            ),
        )
        return ranked[0]

    def _to_signal(self, op: Operation, price: float) -> LegacySignal:
        signal = self._map_signal(op)
        reason = getattr(op, "msg", "") or getattr(op, "mmd", "")
        suggested = self._suggest_action(signal)
        pos_rate = float(getattr(op, "pos_rate", 1.0) or 1.0)
        return LegacySignal(
            signal=signal,
            price=price,
            operation=op,
            suggested_action=suggested,
            reason=reason,
            pos_rate=pos_rate,
        )

    def _map_signal(self, op: Operation) -> str:
        opt = getattr(op, "opt", "").lower()
        mmd = getattr(op, "mmd", "").lower()
        msg = (getattr(op, "msg", "") or "").lower()
        pos_rate = float(getattr(op, "pos_rate", 1.0) or 1.0)

        if opt == "buy":
            return "BUY1"

        if opt == "sell":
            if "stop" in msg or "止损" in msg or "loss" in mmd:
                return "STOP_LOSS"
            if pos_rate >= 0.99 or getattr(op, "close_uid", "") == "clear":
                return "SELL_ALL"
            return "SELL1"

        # Fallback: treat unknown operations as HOLD equivalents
        return "HOLD"

    @staticmethod
    def _suggest_action(signal: str) -> Action:
        if signal == "BUY1":
            return Action.BUY_INITIAL
        if signal == "SELL_ALL" or signal == "STOP_LOSS":
            return Action.SELL_ALL
        if signal == "SELL1":
            return Action.SELL_PARTIAL
        return Action.HOLD


__all__ = [
    "LegacySignal",
    "LegacyStrategyAdapter",
    "LegacyPositionBook",
    "PriceResolver",
]

