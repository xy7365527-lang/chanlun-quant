from datetime import datetime, timedelta

from chanlun_quant.types import Bar
from chanlun_quant.core.fractal import detect_fractals, detect_on_normalized


def _mkbar(ts, o, h, l, c, idx, level="5m"):
    return Bar(timestamp=ts, open=o, high=h, low=l, close=c, volume=0, index=idx, level=level)


def test_detect_fractals_simple_top_bottom():
    t0 = datetime(2024, 1, 1, 9, 30)
    bars = [
        _mkbar(t0 + timedelta(minutes=0), 10, 11, 9, 10.5, 0),
        _mkbar(t0 + timedelta(minutes=1), 10, 12, 9.5, 11, 1),
        _mkbar(t0 + timedelta(minutes=2), 10, 13, 10.2, 12.5, 2),
        _mkbar(t0 + timedelta(minutes=3), 10, 12.2, 9.8, 11.2, 3),
        _mkbar(t0 + timedelta(minutes=4), 10, 11.0, 8.8, 9.1, 4),
        _mkbar(t0 + timedelta(minutes=5), 10, 11.5, 9.5, 10.5, 5),
    ]
    frs = detect_fractals(bars)
    kinds = [f.type for f in frs]
    idxs = [f.index for f in frs]
    assert kinds == ["top", "bottom"], f"unexpected kinds: {kinds}"
    assert idxs == [2, 4], f"unexpected idxs: {idxs}"
    top = frs[0]
    bot = frs[1]
    assert top.price == bars[2].high
    assert bot.price == bars[4].low
    assert top.bar_index == bars[2].index
    assert bot.bar_index == bars[4].index
    assert top.level == bars[2].level
    assert bot.level == bars[4].level


def test_detect_on_normalized_handles_equal_high_low():
    t0 = datetime(2024, 1, 1, 9, 30)
    bars = [
        _mkbar(t0 + timedelta(minutes=0), 10, 11.0, 9.4, 10.3, 0),
        _mkbar(t0 + timedelta(minutes=1), 10, 11.0, 9.6, 10.6, 1),
        _mkbar(t0 + timedelta(minutes=2), 10, 12.0, 10.2, 11.8, 2),
        _mkbar(t0 + timedelta(minutes=3), 10, 11.3, 9.7, 10.9, 3),
        _mkbar(t0 + timedelta(minutes=4), 10, 10.5, 8.8, 9.2, 4),
        _mkbar(t0 + timedelta(minutes=5), 10, 10.9, 9.0, 10.2, 5),
    ]
    frs_norm = detect_on_normalized(bars)
    kinds = [f.type for f in frs_norm]
    assert "top" in kinds and "bottom" in kinds
    assert len(frs_norm) >= 2
