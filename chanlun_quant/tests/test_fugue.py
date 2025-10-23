from chanlun_quant.core.fugue import fuse_levels
from chanlun_quant.types import Signal


def test_fugue_resonance_and_hedge_and_dislocation():
    sig_5m = [Signal(type="BUY1", price=10.0, index=100, level="5m")]
    sig_30m = [Signal(type="BUY2", price=10.5, index=120, level="30m")]
    sig_1d = [Signal(type="BUY3", price=11.0, index=130, level="1d")]
    out = fuse_levels({"5m": sig_5m, "30m": sig_30m, "1d": sig_1d}, disloc_window=50)
    assert out["resonance"] is True
    assert out["hedge"] is False
    assert out["score"] == 1.0
    assert out["dislocation"] is False

    sig_5m_2 = [Signal(type="SELL1", price=9.5, index=160, level="5m")]
    out2 = fuse_levels({"5m": sig_5m_2, "30m": sig_30m, "1d": sig_1d}, disloc_window=50)
    assert out2["hedge"] is True
    assert out2["score"] < 1.0

    sig_5m_3 = [Signal(type="BUY1", price=10.2, index=10, level="5m")]
    out3 = fuse_levels({"5m": sig_5m_3, "30m": sig_30m, "1d": sig_1d}, disloc_window=50)
    assert out3["dislocation"] is True
