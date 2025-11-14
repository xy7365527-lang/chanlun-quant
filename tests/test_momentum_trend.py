from chanlun_quant.core.momentum import (
    area_between,
    area_for_segment,
    area_for_segments,
    area_for_trend,
    compute_macd,
)
from chanlun_quant.types import Fractal, Segment, Stroke, Trend


def _mkstroke(bi, ei, hi, lo, dir_, level="5m"):
    sf = Fractal(
        type="bottom" if dir_ == "up" else "top",
        index=bi,
        price=lo if dir_ == "up" else hi,
        bar_index=bi,
        level=level,
    )
    ef = Fractal(
        type="top" if dir_ == "up" else "bottom",
        index=ei,
        price=hi if dir_ == "up" else lo,
        bar_index=ei,
        level=level,
    )
    return Stroke(
        start_fractal=sf,
        end_fractal=ef,
        direction=dir_,
        high=hi,
        low=lo,
        start_bar_index=bi,
        end_bar_index=ei,
        id=f"{bi}->{ei}",
        level=level,
    )


def _mkseg(strokes, dir_):
    start = strokes[0].start_bar_index
    end = strokes[-1].end_bar_index
    return Segment(strokes=list(strokes), direction=dir_, start_index=start, end_index=end)


def test_trend_area_equals_sum_of_segments():
    closes = [i for i in range(1, 201)]
    macd = compute_macd(closes)
    sA1 = _mkstroke(20, 30, hi=22.0, lo=19.8, dir_="up")
    sA2 = _mkstroke(30, 40, hi=23.0, lo=20.5, dir_="up")
    segA = _mkseg([sA1, sA2], "up")
    sB1 = _mkstroke(60, 75, hi=28.0, lo=24.0, dir_="up")
    sB2 = _mkstroke(75, 90, hi=30.0, lo=25.0, dir_="up")
    segB = _mkseg([sB1, sB2], "up")
    trend = Trend(direction="up", segments=[segA, segB], start_index=20, end_index=90, level="5m")

    a_segA = area_for_segment(macd, segA, mode="hist")
    a_segB = area_for_segment(macd, segB, mode="hist")
    a_trend = area_for_trend(macd, trend, mode="hist")
    assert abs(a_trend - (a_segA + a_segB)) < 1e-9


def test_segments_area_equals_sum_of_intervals():
    closes = [i for i in range(1, 301)]
    macd = compute_macd(closes)
    s1 = _mkstroke(50, 70, hi=18.0, lo=15.0, dir_="up")
    s2 = _mkstroke(71, 90, hi=20.0, lo=16.0, dir_="up")
    seg = _mkseg([s1, s2], "up")
    a_seg = area_for_segment(macd, seg, mode="hist")
    a_sum = area_between(macd, 50, 70, mode="hist") + area_between(macd, 71, 90, mode="hist")
    assert abs(a_seg - a_sum) < 1e-6

    segments_area = area_for_segments(macd, [seg], mode="hist")
    assert abs(segments_area - a_seg) < 1e-9
