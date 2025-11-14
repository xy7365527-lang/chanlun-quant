from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from ib_insync import IB, Contract, Stock, MarketOrder, LimitOrder, Trade

from .interface import BrokerInterface, OrderResult


def _normalize_action(action: str) -> str:
    upper = action.upper()
    if "BUY" in upper:
        return "BUY"
    if "SELL" in upper:
        return "SELL"
    return upper


@dataclass
class IBBroker(BrokerInterface):
    """
    通过 ib_insync 与 IB TWS/Gateway 交互的简单 Broker。

    - 默认使用 config 中的 host/port/clientId。
    - 合约类型默认为 SMART/USD 股票，可通过 exchange/currency 覆盖。
    - place_order 会根据是否提供 price 选择市价/限价单，并等待成交结果。
    """

    host: str
    port: int
    client_id: int
    exchange: str = "SMART"
    currency: str = "USD"
    qualify_contracts: bool = True
    _ib: IB = field(default_factory=IB, init=False, repr=False)
    _contracts: Dict[Tuple[str, str, str], Contract] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self.connect()

    def connect(self) -> None:
        if not self._ib.isConnected():
            self._ib.connect(self.host, self.port, clientId=self.client_id)

    def disconnect(self) -> None:
        if self._ib.isConnected():
            self._ib.disconnect()

    def _contract(self, symbol: str) -> Contract:
        key = (symbol, self.exchange, self.currency)
        if key not in self._contracts:
            contract = Stock(symbol, self.exchange, self.currency)
            if self.qualify_contracts:
                qualified = self._ib.qualifyContracts(contract)
                if qualified:
                    contract = qualified[0]
            self._contracts[key] = contract
        return self._contracts[key]

    def _place_trade(self, symbol: str, quantity: float, price: Optional[float], order_side: str) -> Trade:
        contract = self._contract(symbol)
        qty = abs(float(quantity))
        action = order_side.upper()
        if price and price > 0:
            order = LimitOrder(action, qty, price)
        else:
            order = MarketOrder(action, qty)
        trade = self._ib.placeOrder(contract, order)
        trade.sleepUntilCompleted()
        return trade

    def place_order(self, action: str, quantity: float, symbol: str, price: float | None = None) -> OrderResult:
        self.connect()
        order_side = _normalize_action(action)
        if order_side not in {"BUY", "SELL"}:
            return OrderResult(status="ignored", action=action, quantity=quantity, symbol=symbol, price=price)

        trade = self._place_trade(symbol, quantity, price, order_side)
        status = trade.orderStatus.status
        avg_fill = trade.orderStatus.avgFillPrice or price
        metadata = {
            "orderId": trade.order.orderId,
            "permid": trade.order.permId,
            "filled": trade.orderStatus.filled,
        }
        return OrderResult(
            status=status,
            action=action,
            quantity=quantity,
            symbol=symbol,
            price=avg_fill,
            metadata=metadata,
        )

    def cancel_all(self) -> None:
        self.connect()
        for trade in list(self._ib.trades()):
            if trade.orderStatus.status not in {"Filled", "Cancelled"}:
                self._ib.cancelOrder(trade.order)

    def current_position(self) -> Dict[str, float]:
        self.connect()
        positions = self._ib.positions()
        if not positions:
            return {"quantity": 0.0, "avg_price": 0.0}
        total_qty = 0.0
        weighted_price = 0.0
        for pos in positions:
            if pos.contract.currency != self.currency:
                continue
            total_qty += pos.position
            weighted_price += pos.position * pos.avgCost
        avg_price = weighted_price / total_qty if total_qty else 0.0
        return {"quantity": total_qty, "avg_price": avg_price}

    # Optional context manager helpers
    def __enter__(self) -> "IBBroker":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()


__all__ = ["IBBroker"]

