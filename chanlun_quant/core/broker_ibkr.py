from __future__ import annotations

from typing import Any, Dict, List


class IBKRBroker:
    """IBKR 适配器骨架：保持 execute 签名与 Broker 一致，真实实现时接入 IBKR API"""

    def __init__(self, account: str = "", host: str = "127.0.0.1", port: int = 7497, client_id: int = 1) -> None:
        self.account = account
        self.host = host
        self.port = port
        self.client_id = client_id

    def execute(self, symbol: str, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        fills: List[Dict[str, Any]] = []
        for order in orders:
            price = None
            if order.get("price_band"):
                lo = min(order["price_band"])
                hi = max(order["price_band"])
                price = (lo + hi) / 2.0
            fills.append({**order, "price": price})
        return fills
