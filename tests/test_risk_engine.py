from chanlun_quant.core.risk import RiskEngine, RiskLimits


def test_idempotent_block():
    engine = RiskEngine(RiskLimits())
    orders = [{"bucket": "segment", "side": "sell", "qty": 10}]
    assert not engine.should_block(core_qty=1000, envelope_child_ratio=0.3, proposals=orders)
    engine.on_orders_sent(orders)
    assert engine.should_block(core_qty=1000, envelope_child_ratio=0.3, proposals=orders)
    assert engine.state.blocked_reason == "idempotent_same_plan"


def test_envelope_child_ratio_block():
    engine = RiskEngine(RiskLimits(max_child_ratio=0.2))
    orders = [{"bucket": "segment", "side": "sell", "qty": 10}]
    assert engine.should_block(core_qty=1000, envelope_child_ratio=0.35, proposals=orders)
    assert engine.state.blocked_reason == "child_ratio_exceed"
