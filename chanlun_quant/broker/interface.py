"""Broker interfaces: abstract + simulated."""


class BrokerInterface:
    def place_order(self, action: str, quantity: float, symbol: str, price: float | None = None):
        raise NotImplementedError


class SimulatedBroker(BrokerInterface):
    def place_order(self, action: str, quantity: float, symbol: str, price: float | None = None):
        return {"status": "filled", "action": action, "qty": quantity, "symbol": symbol, "price": price}
