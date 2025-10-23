from chanlun_quant.analysis.multilevel import (
    build_multilevel_mapping,
    interval_nesting_for_segment,
    map_segments_low_to_high,
    map_strokes_low_to_high,
)
from chanlun_quant.types import Fractal, Segment, Stroke


def _mkstroke(bi, ei, hi, lo, dir_, lvl="5m"):
    sf = Fractal(type="bottom" if dir_ == "up" else "top", index=bi, price=lo if dir_ == "up" else hi, bar_index=bi, level=lvl)
    ef = Fractal(type="top" if dir_ == "up" else "bottom", index=ei, price=hi if dir_ == "up" else lo, bar_index=ei, level=lvl)
    return Stroke(
        start_fractal=sf,
        end_fractal=ef,
        direction=dir_,
        high=hi,
        low=lo,
        start_bar_index=bi,
        end_bar_index=ei,
        id=f"{bi}->{ei}",
        level=lvl,
    )


def _mkseg(strokes, dir_, lvl="5m"):
    start = strokes[0].start_bar_index
    end = strokes[-1].end_bar_index
    return Segment(strokes=list(strokes), direction=dir_, start_index=start, end_index=end, level=lvl)


def test_map_strokes_and_segments_and_nesting():
    high_strokes = [
        _mkstroke(0, 100, hi=20, lo=10, dir_="up", lvl="30m"),
        _mkstroke(100, 200, hi=22, lo=12, dir_="down", lvl="30m"),
    ]
    low_strokes = [
        _mkstroke(10, 30, hi=15, lo=11, dir_="up", lvl="5m"),
        _mkstroke(30, 50, hi=16, lo=12, dir_="down", lvl="5m"),
        _mkstroke(50, 70, hi=17, lo=13, dir_="up", lvl="5m"),
    ]
    high_segs = [
        _mkseg([high_strokes[0]], "up", lvl="30m"),
        _mkseg([high_strokes[1]], "down", lvl="30m"),
    ]
    low_segs = [
        _mkseg(low_strokes[:2], "down", lvl="5m"),
        _mkseg(low_strokes[2:], "up", lvl="5m"),
    ]

    for hs in high_strokes:
        hs.lower_level_children = []
    map_strokes_low_to_high(low_strokes, high_strokes)
    assert all(stroke.high_level_parent is not None for stroke in low_strokes)
    assert len(high_strokes[0].lower_level_children) >= 1

    for hg in high_segs:
        hg.child_segments = []
    mapping = map_segments_low_to_high(low_segs, high_segs)
    assert any(parent_idx == 0 for parent_idx in mapping.values())

    nest = interval_nesting_for_segment(high_segs[0], low_segs)
    assert "time_cover_count" in nest and nest["time_cover_count"] >= 1
    assert isinstance(nest["price_full_nesting"], bool)

    result = build_multilevel_mapping("5m", "30m", low_strokes, high_strokes, low_segs, high_segs)
    assert result["stroke_mapping_done"] is True
    assert isinstance(result["segment_mapping"], dict)
    assert isinstance(result["nesting"], dict)
