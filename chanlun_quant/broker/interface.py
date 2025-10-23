"""Broker interfaces: abstract + simulated."""


class BrokerInterface:
    def place_order(self, action: str, quantity: float, symbol: str, price: float | None = None):
        raise NotImplementedError


class SimulatedBroker(BrokerInterface):
    def place_order(self, action: str, quantity: float, symbol: str, price: float | None = None):
        return {"status": "filled", "action": action, "qty": quantity, "symbol": symbol, "price": price}


class ExternalBrokerAdapter(BrokerInterface):
    """Wrap an arbitrary broker implementation with a minimal adapter."""

    def __init__(self, ext: object) -> None:
        self.ext = ext

    def place_order(self, action: str, quantity: float, symbol: str, price: float | None = None):
        if hasattr(self.ext, "place_order"):
            return self.ext.place_order(action, quantity, symbol, price)
        if hasattr(self.ext, "order"):
            return self.ext.order(side=action, qty=quantity, symbol=symbol, price=price)
        if hasattr(self.ext, "send_order"):
            return self.ext.send_order(action, quantity, symbol, price)
        return {
            "status": "submitted",
            "action": action,
            "qty": quantity,
            "symbol": symbol,
            "price": price,
            "_adapter": "external",
        }
