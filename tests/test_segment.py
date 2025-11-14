from datetime import datetime, timedelta

from chanlun_quant.types import Bar, Fractal, Stroke
from chanlun_quant.core.segment import build_segments


def _mkbar(ts, o, h, l, c, idx, level="5m"):
    return Bar(timestamp=ts, open=o, high=h, low=l, close=c, volume=0, index=idx, level=level)


def _mkstroke(bi, ei, dir_, bars):
    sl = min(bi, ei)
    sr = max(bi, ei)
    hi = max(b.high for b in bars[sl : sr + 1])
    lo = min(b.low for b in bars[sl : sr + 1])
    sf = Fractal(
        type="bottom" if dir_ == "up" else "top",
        index=bi,
        price=bars[bi].low if dir_ == "up" else bars[bi].high,
        bar_index=bars[bi].index,
        level=bars[bi].level,
    )
    ef = Fractal(
        type="top" if dir_ == "up" else "bottom",
        index=ei,
        price=bars[ei].high if dir_ == "up" else bars[ei].low,
        bar_index=bars[ei].index,
        level=bars[ei].level,
    )
    return Stroke(
        start_fractal=sf,
        end_fractal=ef,
        direction=dir_,
        high=hi,
        low=lo,
        start_bar_index=bars[bi].index,
        end_bar_index=bars[ei].index,
        id=f"{bi}->{ei}",
        level=bars[bi].level,
    )


def test_segment_end_when_no_gap_overlaps():
    t0 = datetime(2024, 1, 1, 9, 30)
    bars = [
        _mkbar(t0 + timedelta(minutes=0), 10, 11, 9.8, 10.5, 0),
        _mkbar(t0 + timedelta(minutes=1), 10, 12.5, 10.2, 12.1, 1),
        _mkbar(t0 + timedelta(minutes=2), 10, 11.8, 9.9, 10.8, 2),
        _mkbar(t0 + timedelta(minutes=3), 10, 13.0, 11.0, 12.8, 3),
        _mkbar(t0 + timedelta(minutes=4), 10, 12.2, 10.6, 11.0, 4),
        _mkbar(t0 + timedelta(minutes=5), 10, 12.1, 10.7, 11.6, 5),
    ]
    s1 = _mkstroke(0, 1, "up", bars)
    x1 = _mkstroke(1, 2, "down", bars)
    s2 = _mkstroke(2, 3, "up", bars)
    x2 = _mkstroke(3, 4, "down", bars)
    segs = build_segments([s1, x1, s2, x2], strict_feature_sequence=True, gap_tolerance=0.0)
    assert segs, "expected at least one segment"
    first_seg = segs[0]
    assert first_seg.direction == "up"
    assert first_seg.end_index == s2.end_bar_index
    assert first_seg.end_confirmed is True


def test_segment_gap_needs_confirmation_in_strict_mode():
    t0 = datetime(2024, 1, 1, 9, 30)
    bars = [
        _mkbar(t0 + timedelta(minutes=0), 10, 11.0, 10.0, 10.9, 0),
        _mkbar(t0 + timedelta(minutes=1), 10, 12.5, 11.5, 12.0, 1),
        _mkbar(t0 + timedelta(minutes=2), 10, 12.0, 11.6, 11.8, 2),
        _mkbar(t0 + timedelta(minutes=3), 10, 13.2, 12.2, 13.1, 3),
        _mkbar(t0 + timedelta(minutes=4), 10, 11.5, 10.5, 10.7, 4),
    ]
    s1 = _mkstroke(0, 1, "up", bars)
    x1 = _mkstroke(1, 2, "down", bars)
    s2 = _mkstroke(2, 3, "up", bars)
    x2 = _mkstroke(3, 4, "down", bars)
    # 调整 x2 的高低区间以制造缺口
    x2.high = 9.5
    x2.low = 8.9
    x2.start_fractal.price = x2.high
    x2.end_fractal.price = x2.low

    segs_strict = build_segments([s1, x1, s2, x2], strict_feature_sequence=True, gap_tolerance=0.0)
    assert segs_strict[-1].end_confirmed is False

    segs_loose = build_segments([s1, x1, s2, x2], strict_feature_sequence=False, gap_tolerance=0.0)
    assert segs_loose[0].end_index == s2.end_bar_index
    assert segs_loose[0].end_confirmed is False
