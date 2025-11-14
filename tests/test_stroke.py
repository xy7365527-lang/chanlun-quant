from datetime import datetime, timedelta

from chanlun_quant.types import Bar, Fractal
from chanlun_quant.core.stroke import build_strokes


def _mkbar(ts, o, h, l, c, idx, level="5m"):
    return Bar(timestamp=ts, open=o, high=h, low=l, close=c, volume=0, index=idx, level=level)


def test_build_strokes_basic_min3():
    """
    构造一个最小用例：
    - bottom(0)->top(2) 上行笔
    - top(2)->bottom(4) 下行笔
    min_bars_per_pen=3 可满足；若=5 则因为跨度不足而不成笔。
    """
    t0 = datetime(2024, 1, 1, 9, 30)
    bars = [
        _mkbar(t0 + timedelta(minutes=0), 10, 11.0, 9.6, 10.4, 0),
        _mkbar(t0 + timedelta(minutes=1), 10, 12.0, 10.0, 11.5, 1),
        _mkbar(t0 + timedelta(minutes=2), 10, 13.5, 10.7, 13.0, 2),
        _mkbar(t0 + timedelta(minutes=3), 10, 12.2, 9.8, 11.2, 3),
        _mkbar(t0 + timedelta(minutes=4), 10, 11.0, 8.7, 9.2, 4),
        _mkbar(t0 + timedelta(minutes=5), 10, 11.3, 9.0, 10.5, 5),
    ]
    frs = [
        Fractal(type="bottom", index=0, price=bars[0].low, bar_index=bars[0].index, level="5m"),
        Fractal(type="top", index=2, price=bars[2].high, bar_index=bars[2].index, level="5m"),
        Fractal(type="bottom", index=4, price=bars[4].low, bar_index=bars[4].index, level="5m"),
    ]
    strokes = build_strokes(frs, bars, min_bars_per_pen=3)
    assert len(strokes) == 2
    assert strokes[0].direction == "up"
    assert strokes[1].direction == "down"
    assert strokes[0].high == max(b.high for b in bars[0:3])
    assert strokes[0].low == min(b.low for b in bars[0:3])
    assert strokes[1].high == max(b.high for b in bars[2:5])
    assert strokes[1].low == min(b.low for b in bars[2:5])
    assert strokes[0].start_bar_index == bars[0].index
    assert strokes[0].end_bar_index == bars[2].index
    assert strokes[1].start_bar_index == bars[2].index
    assert strokes[1].end_bar_index == bars[4].index


def test_min_bars_constraint_enforced():
    """
    当 min_bars_per_pen=5 时，跨度不足的 fractal 配对不应成笔。
    """
    t0 = datetime(2024, 1, 1, 9, 30)
    bars = [
        _mkbar(t0 + timedelta(minutes=0), 10, 11, 9.6, 10.4, 0),
        _mkbar(t0 + timedelta(minutes=1), 10, 12, 10.0, 11.5, 1),
        _mkbar(t0 + timedelta(minutes=2), 10, 13, 10.7, 12.8, 2),
        _mkbar(t0 + timedelta(minutes=3), 10, 12, 9.9, 11.2, 3),
        _mkbar(t0 + timedelta(minutes=4), 10, 11, 9.0, 9.3, 4),
    ]
    frs = [
        Fractal(type="bottom", index=0, price=bars[0].low, bar_index=0, level="5m"),
        Fractal(type="top", index=2, price=bars[2].high, bar_index=2, level="5m"),
        Fractal(type="bottom", index=4, price=bars[4].low, bar_index=4, level="5m"),
    ]
    strokes_strict = build_strokes(frs, bars, min_bars_per_pen=5)
    assert len(strokes_strict) == 0


def test_exceed_constraint_skips_invalid_pair():
    """
    当不满足超越约束（例如上行笔但 end.price <= start.price），该配对应被跳过。
    """
    t0 = datetime(2024, 1, 1, 9, 30)
    bars = [
        _mkbar(t0 + timedelta(minutes=0), 10, 11, 9.6, 10.4, 0),
        _mkbar(t0 + timedelta(minutes=1), 10, 11.1, 9.8, 10.6, 1),
        _mkbar(t0 + timedelta(minutes=2), 10, 11.2, 10.0, 10.7, 2),
        _mkbar(t0 + timedelta(minutes=3), 10, 11.0, 9.7, 10.2, 3),
        _mkbar(t0 + timedelta(minutes=4), 10, 10.9, 9.5, 10.0, 4),
        _mkbar(t0 + timedelta(minutes=5), 10, 11.5, 9.9, 10.8, 5),
    ]
    frs = [
        Fractal(type="bottom", index=0, price=bars[0].low, bar_index=0, level="5m"),
        Fractal(type="top", index=1, price=bars[1].high, bar_index=1, level="5m"),
        Fractal(type="top", index=2, price=bars[2].high, bar_index=2, level="5m"),
        Fractal(type="bottom", index=4, price=bars[4].low, bar_index=4, level="5m"),
    ]
    strokes = build_strokes(frs, bars, min_bars_per_pen=3)
    for s in strokes:
        if s.direction == "up":
            assert s.end_fractal.price > s.start_fractal.price
        else:
            assert s.end_fractal.price < s.start_fractal.price
