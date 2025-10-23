from chanlun_quant.core.momentum import (
    area_between,
    area_for_segment,
    area_for_segments,
    area_for_stroke,
    compute_macd,
    ema,
    is_trend_divergent,
)
from chanlun_quant.types import Fractal, Segment, Stroke


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


def test_ema_and_macd_shapes():
    closes = [i for i in range(1, 51)]
    e5 = ema(closes, 5)
    e20 = ema(closes, 20)
    assert len(e5) == len(closes) and len(e20) == len(closes)
    assert e5[-1] > e20[-1]
    macd = compute_macd(closes)
    assert set(macd.keys()) == {"dif", "dea", "hist"}
    assert len(macd["dif"]) == len(closes)
    assert macd["hist"][-1] > -1e-8


def test_area_functions_consistency():
    closes = [i for i in range(1, 201)]
    macd = compute_macd(closes)
    stroke = _mkstroke(20, 40, hi=25.0, lo=19.5, dir_="up")
    seg = _mkseg([stroke], "up")
    seg2 = _mkseg([_mkstroke(60, 80, hi=30.0, lo=22.0, dir_="up")], "up")

    area_hist = area_between(macd, 20, 40, mode="hist")
    area_dif = area_between(macd, 20, 40, mode="dif")
    area_abs = area_between(macd, 20, 40, mode="abs_hist")
    assert isinstance(area_hist, float)
    assert isinstance(area_dif, float)
    assert area_abs >= 0.0

    assert area_for_stroke(macd, stroke, mode="hist") == area_hist
    assert area_for_segment(macd, seg, mode="hist") == area_hist

    total = area_for_segments(macd, [seg, seg2], mode="hist")
    assert abs(total - (area_for_segment(macd, seg, "hist") + area_for_segment(macd, seg2, "hist"))) < 1e-9


def test_segment_area_and_divergence_uptrend():
    closes = [i for i in range(1, 160)]
    macd = compute_macd(closes)

    sA1 = _mkstroke(30, 45, hi=35.0, lo=28.0, dir_="up")
    sA2 = _mkstroke(45, 55, hi=36.0, lo=29.0, dir_="up")
    segA = _mkseg([sA1, sA2], "up")

    sC1 = _mkstroke(90, 100, hi=38.0, lo=32.0, dir_="up")
    sC2 = _mkstroke(100, 110, hi=39.5, lo=33.0, dir_="up")
    segC = _mkseg([sC1, sC2], "up")

    aA = abs(area_for_segment(macd, segA, mode="hist"))
    aC = abs(area_for_segment(macd, segC, mode="hist"))
    assert aC < 0.8 * aA
    assert is_trend_divergent(segA, segC, macd, threshold=0.8, area_mode="hist") is True


def test_divergence_requires_new_extreme():
    closes = [i for i in range(1, 140)]
    macd = compute_macd(closes)

    sA1 = _mkstroke(20, 30, hi=25.0, lo=18.0, dir_="up")
    sA2 = _mkstroke(30, 40, hi=26.0, lo=19.0, dir_="up")
    segA = _mkseg([sA1, sA2], "up")

    sC1 = _mkstroke(70, 80, hi=25.5, lo=20.0, dir_="up")
    sC2 = _mkstroke(80, 90, hi=25.5, lo=20.5, dir_="up")
    segC = _mkseg([sC1, sC2], "up")

    assert is_trend_divergent(segA, segC, macd, threshold=0.9, area_mode="hist") is False
