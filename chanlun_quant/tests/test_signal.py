from chanlun_quant.types import Central, Fractal, Segment, Signal, Stroke
from chanlun_quant.core.signal import detect_signals


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


class CfgMock:
    divergence_threshold = 0.8
    macd_area_mode = "hist"


def test_buy1_sell1_divergence_minimal():
    down_A = _mkseg([_mkstroke(10, 18, hi=15, lo=11, dir_="down")], "down")
    down_C = _mkseg([_mkstroke(20, 28, hi=14, lo=10, dir_="down")], "down")
    up_A2 = _mkseg([_mkstroke(30, 38, hi=15, lo=12, dir_="up")], "up")
    up_C2 = _mkseg([_mkstroke(40, 48, hi=16, lo=13, dir_="up")], "up")
    segs = [down_A, down_C, up_A2, up_C2]

    max_idx = max(s.end_index for s in segs) + 5
    hist = [0.0] * (max_idx + 1)
    for i in range(10, 19):
        hist[i] = -0.8
    for i in range(20, 29):
        hist[i] = -0.3
    for i in range(30, 39):
        hist[i] = 0.8
    for i in range(40, 49):
        hist[i] = 0.3
    macd = {"dif": [0.0] * (max_idx + 1), "dea": [0.0] * (max_idx + 1), "hist": hist}

    sigs = detect_signals(segs, centrals=[], macd=macd, cfg=CfgMock())
    kinds = sorted(s.type for s in sigs)
    assert "BUY1" in kinds and "SELL1" in kinds


def test_buy2_non_new_low_and_buy3_central_pullback():
    d1 = _mkseg([_mkstroke(10, 18, hi=15, lo=10.0, dir_="down")], "down")
    u1 = _mkseg([_mkstroke(18, 24, hi=13, lo=11.5, dir_="up")], "up")
    d2 = _mkseg([_mkstroke(24, 30, hi=12, lo=10.2, dir_="down")], "down")
    segs = [d1, u1, d2]

    central = Central(
        level="5m",
        zg=11.8,
        zd=9.8,
        start_index=10,
        end_index=24,
        stroke_indices=[0, 1, 2],
        extended=False,
        expanded=False,
        newborn=False,
    )
    breakout = _mkseg([_mkstroke(24, 34, hi=14.0, lo=12.0, dir_="up")], "up")
    pullback = _mkseg([_mkstroke(34, 40, hi=12.1, lo=10.1, dir_="down")], "down")
    segs2 = [d1, u1, d2, breakout, pullback]

    max_idx = max(s.end_index for s in segs2) + 3
    macd = {"dif": [0.0] * (max_idx + 1), "dea": [0.0] * (max_idx + 1), "hist": [0.0] * (max_idx + 1)}

    sigs1 = detect_signals(segs, centrals=[], macd=macd, cfg=CfgMock())
    kinds1 = [s.type for s in sigs1]
    assert "BUY2" in kinds1

    sigs2 = detect_signals(segs2, centrals=[central], macd=macd, cfg=CfgMock())
    kinds2 = [s.type for s in sigs2]
    assert "BUY3" in kinds2
