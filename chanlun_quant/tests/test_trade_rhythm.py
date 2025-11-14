from chanlun_quant.strategy.position_manager import HoldingManager
from chanlun_quant.strategy.trade_rhythm import TradeRhythmEngine
from chanlun_quant.types import PositionState


def test_trade_rhythm_partial_cycle_reduces_cost() -> None:
    manager = HoldingManager()
    engine = TradeRhythmEngine()

    cfg = type("cfg", (), {"initial_buy_quantity": 1000, "partial_sell_ratio": 0.5, "profit_buy_quantity": 500})

    plan = engine.on_signal("BUY1", 10.0, cfg)
    assert plan["action"].value == "BUY_INITIAL"
    manager.buy(price=10.0, quantity=plan["quantity"])
    assert manager.state.quantity == 1000

    plan = engine.on_signal("SELL1", 12.0, cfg)
    manager.sell(price=12.0, quantity=plan["quantity"])
    assert manager.state.realized_profit == 1000.0

    plan = engine.on_signal("BUY1", 11.0, cfg)
    manager.buy(price=11.0, quantity=plan["quantity"])
    assert manager.state.quantity >= 1000
    assert manager.state.avg_cost <= 10.0


def test_holding_manager_free_ride_flag() -> None:
    manager = HoldingManager()
    manager.buy(price=10.0, quantity=1000, is_initial_buy=True)
    manager.sell(price=20.0, quantity=1000)
    assert manager.state.quantity == 0

    manager.buy(price=5.0, quantity=1000)
    assert manager.state.avg_cost == 0.0
    assert manager.state.free_ride is True
    assert manager.state.stage == "PROFIT_HOLD"
