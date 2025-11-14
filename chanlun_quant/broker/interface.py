"""Broker interfaces: abstract + simulated."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class OrderResult:
    status: str
    action: str
    quantity: float
    symbol: str
    price: Optional[float] = None
    metadata: Dict[str, object] | None = None


class BrokerInterface:
    def place_order(self, action: str, quantity: float, symbol: str, price: float | None = None) -> OrderResult:
        raise NotImplementedError

    def cancel_all(self) -> None:
        raise NotImplementedError

    def current_position(self) -> Dict[str, float]:
        raise NotImplementedError


class SimulatedBroker(BrokerInterface):
    def __init__(self, *, initial_cash: float = 1_000_000.0) -> None:
        self.cash = initial_cash
        self.position = 0.0
        self.avg_price = 0.0
        self.last_order: Optional[OrderResult] = None

    def place_order(self, action: str, quantity: float, symbol: str, price: float | None = None) -> OrderResult:
        action_lower = action.lower()
        qty = float(quantity)
        price = float(price) if price is not None else price

        if action_lower.startswith("buy"):
            if price is not None:
                cost = qty * price
                self.cash -= cost
                total_position_value = self.avg_price * self.position + cost
                self.position += qty
                if self.position > 0:
                    self.avg_price = total_position_value / self.position
        elif action_lower.startswith("sell"):
            if price is not None:
                proceeds = qty * price
                self.cash += proceeds
            self.position -= qty
            if self.position <= 0:
                self.position = 0.0
                self.avg_price = 0.0

        result = OrderResult(status="filled", action=action, quantity=qty, symbol=symbol, price=price)
        self.last_order = result
        return result

    def cancel_all(self) -> None:
        return None

    def current_position(self) -> Dict[str, float]:
        return {"quantity": self.position, "avg_price": self.avg_price, "cash": self.cash}


class ExternalBrokerAdapter(BrokerInterface):
    """Wrap an arbitrary broker implementation with a minimal adapter."""

    def __init__(self, ext: object) -> None:
        self.ext = ext

    def place_order(self, action: str, quantity: float, symbol: str, price: float | None = None) -> OrderResult:
        if hasattr(self.ext, "place_order"):
            result = self.ext.place_order(action, quantity, symbol, price)
        elif hasattr(self.ext, "order"):
            result = self.ext.order(side=action, qty=quantity, symbol=symbol, price=price)
        elif hasattr(self.ext, "send_order"):
            result = self.ext.send_order(action, quantity, symbol, price)
        else:
            result = {
                "status": "submitted",
                "action": action,
                "qty": quantity,
                "symbol": symbol,
                "price": price,
                "_adapter": "external",
            }
        if isinstance(result, OrderResult):
            return result
        return OrderResult(status=str(result.get("status", "submitted")), action=action, quantity=float(quantity), symbol=symbol, price=price, metadata={"raw": result})

    def cancel_all(self) -> None:
        if hasattr(self.ext, "cancel_all"):
            return self.ext.cancel_all()
        if hasattr(self.ext, "cancel_orders"):
            return self.ext.cancel_orders()
        return None

    def current_position(self) -> Dict[str, float]:
        if hasattr(self.ext, "current_position"):
            return self.ext.current_position()
        return {}
