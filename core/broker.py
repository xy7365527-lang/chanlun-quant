from __future__ import annotations

from typing import Any, Dict, List


class Broker:
    """统一下单接口占位：回测/实盘实现应复用此签名。"""

    def execute(self, symbol: str, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """执行订单，返回成交信息 [{'bucket','side','qty','price'}]。MVP：假定即时成交，price=None。"""
        fills: List[Dict[str, Any]] = []
        for order in orders:
            fills.append({**order, "price": order.get("price")})
        return fills

