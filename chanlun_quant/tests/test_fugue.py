from chanlun_quant.core.fugue import fuse_levels
from chanlun_quant.types import Signal


def test_fugue_resonance_output_enriched_fields() -> None:
    sig_5m = [Signal(type="BUY1", price=10.0, index=100, level="5m")]
    sig_30m = [Signal(type="BUY2", price=10.5, index=120, level="30m")]
    sig_1d = [Signal(type="BUY3", price=11.0, index=130, level="1d")]
    out = fuse_levels({"5m": sig_5m, "30m": sig_30m, "1d": sig_1d}, disloc_window=50)

    assert out["resonance"] is True
    assert out["hedge"] is False
    assert out["dislocation"] is False
    assert out["state_label"] == "共振上行"
    assert out["dominant_direction"] == 1
    assert out["score"] == 1.0
    assert out["confidence"] == 1.0
    assert "多头共振" in out["commentary"]
    assert len(out["level_details"]) == 3


def test_fugue_detects_hedge_and_penalizes_confidence() -> None:
    sig_5m = [Signal(type="SELL1", price=9.5, index=160, level="5m")]
    sig_30m = [Signal(type="BUY2", price=10.5, index=120, level="30m")]
    sig_1d = [Signal(type="BUY3", price=11.0, index=130, level="1d")]
    out = fuse_levels({"5m": sig_5m, "30m": sig_30m, "1d": sig_1d}, disloc_window=50)

    assert out["hedge"] is True
    assert out["resonance"] is False
    assert out["state_label"] == "级别对冲"
    assert out["dominant_direction"] == 1
    assert out["score"] < 1.0
    assert out["confidence"] < out["score"]


def test_fugue_flags_dislocation() -> None:
    sig_5m = [Signal(type="BUY1", price=10.2, index=10, level="5m")]
    sig_30m = [Signal(type="BUY2", price=10.5, index=120, level="30m")]
    sig_1d = [Signal(type="BUY3", price=11.0, index=130, level="1d")]
    out = fuse_levels({"5m": sig_5m, "30m": sig_30m, "1d": sig_1d}, disloc_window=50)

    assert out["dislocation"] is True
    assert out["max_index_gap"] == 120
    assert out["confidence"] < out["score"]
