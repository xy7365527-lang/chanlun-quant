from datetime import datetime, timedelta

from chanlun_quant.core.kline import merge_containment, normalize
from chanlun_quant.types import Bar


def _bar(idx: int, high: float, low: float, *, open_: float | None = None, close: float | None = None) -> Bar:
    base_time = datetime(2024, 1, 1)
    open_val = open_ if open_ is not None else low
    close_val = close if close is not None else high
    return Bar(
        timestamp=base_time + timedelta(minutes=idx),
        open=open_val,
        high=high,
        low=low,
        close=close_val,
        volume=100.0 + idx,
        index=idx,
        level="5m",
    )


def test_inside_bar_is_merged():
    bars = [
        _bar(0, high=10.0, low=5.0, open_=6.0, close=9.0),
        _bar(1, high=9.0, low=6.0, open_=6.5, close=8.5),
    ]

    merged = merge_containment(bars)

    assert len(merged) == 1
    single = merged[0]
    assert single.high == 10.0
    assert single.low == 6.0
    assert single.index == 1
    assert single.open == bars[1].open


def test_outside_bar_replaces_previous():
    bars = [
        _bar(0, high=9.0, low=6.0),
        _bar(1, high=11.0, low=4.0),
    ]

    merged = merge_containment(bars)

    assert len(merged) == 1
    single = merged[0]
    assert single.high == 11.0
    assert single.low == 4.0
    assert single.index == 1


def test_consecutive_inside_bars_backtrack():
    bars = [
        _bar(0, high=10.0, low=5.0),
        _bar(1, high=9.0, low=5.0),
        _bar(2, high=8.0, low=5.0),
    ]

    merged = merge_containment(bars)

    assert len(merged) == 1
    single = merged[0]
    assert single.high == 8.0
    assert single.low == 5.0


def test_gap_bars_remain_unchanged():
    bars = [
        _bar(0, high=10.0, low=9.5),
        _bar(1, high=12.0, low=11.5),
    ]

    merged = merge_containment(bars)

    assert len(merged) == 2
    assert merged == normalize(bars)
