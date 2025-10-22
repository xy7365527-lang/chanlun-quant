from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any

from chanlun.exchange.exchange_ib import ExchangeIB


@dataclass
class TradeExecutionOptions:
    symbol: str
    amount: float
    side: str  # "long" or "short"
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    leverage: Optional[int] = None
    percentage: Optional[float] = None  # partial close when same side
    note: str = ""


@dataclass
class PositionSnapshot:
    side: str
    size: float
    avg_price: float


class IBOrderExecutor:
    """
    Thin execution helper mirroring the binance executor pattern from nof1.ai.
    """

    def __init__(self, exchange: Optional[ExchangeIB] = None):
        self.exchange = exchange or ExchangeIB()

    def fetch_position(self, symbol: str) -> Optional[PositionSnapshot]:
        positions = self.exchange.positions(symbol)
        if not positions:
            return None
        pos = positions[0]
        size = float(pos.get("position", 0) or 0)
        if size == 0:
            return None
        side = "long" if size > 0 else "short"
        avg_price = float(pos.get("avgCost", 0) or 0)
        return PositionSnapshot(side=side, size=abs(size), avg_price=avg_price)

    def _close_position(
        self, symbol: str, position: PositionSnapshot, percentage: float = 100.0
    ) -> Optional[Dict[str, Any]]:
        pct = max(min(percentage, 100.0), 0.0)
        qty = position.size * pct / 100.0
        if qty <= 0:
            return None
        order_side = "sell" if position.side == "long" else "buy"
        return self.exchange.order(symbol, order_side, qty)

    def close(self, symbol: str, percentage: float = 100.0) -> Optional[Dict[str, Any]]:
        current = self.fetch_position(symbol)
        if current is None:
            return None
        return self._close_position(symbol, current, percentage)

    def _open_position(
        self, symbol: str, side: str, amount: float
    ) -> Optional[Dict[str, Any]]:
        if amount <= 0:
            return None
        order_side = "buy" if side == "long" else "sell"
        return self.exchange.order(symbol, order_side, amount)

    def execute(self, options: TradeExecutionOptions) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Close opposing positions if necessary, optionally partially scale out,
        then open desired direction. Returns {"closed": ..., "opened": ...}.
        """
        symbol = options.symbol.upper()
        amount = float(options.amount)
        side = options.side

        closed = None
        current = self.fetch_position(symbol)
        if current:
            if current.side != side:
                closed = self._close_position(symbol, current, 100.0)
            elif options.percentage:
                closed = self._close_position(symbol, current, options.percentage)

        opened = self._open_position(symbol, side, amount)

        return {"closed": closed, "opened": opened}

    def adjust_stops(self, options: TradeExecutionOptions):
        """
        Placeholder to align with nof1.ai API; IB stop management to be implemented.
        """
        return None
