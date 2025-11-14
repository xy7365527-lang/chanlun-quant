from __future__ import annotations

from typing import Any, Dict, List


class BacktestBroker:
    def __init__(self, fee_bps: float = 4.0, slippage_bps: float = 3.0) -> None:
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps

    def execute(self, symbol: str, orders: List[Dict[str, Any]], last_price: float) -> List[Dict[str, Any]]:
        fills: List[Dict[str, Any]] = []
        for order in orders:
            side = order["side"]
            qty = float(order["qty"])
            direction = 1 if side == "buy" else -1
            price = last_price * (1 + direction * self.slippage_bps / 1e4)
            fee = abs(price * qty) * (self.fee_bps / 1e4)
            fills.append({**order, "price": price, "fee": fee})
        return fills

