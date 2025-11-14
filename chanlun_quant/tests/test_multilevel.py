from __future__ import annotations

from chanlun_quant.analysis.multilevel import analyze_relation_matrix, build_multilevel_mapping, interval_nesting_for_segment
from chanlun_quant.types import Segment, Stroke, StructureLevelState, Trend


def _make_stroke(level: str, start: int, end: int, direction: str, high: float, low: float) -> Stroke:
    return Stroke(
        start_fractal=None,  # type: ignore[arg-type]
        end_fractal=None,  # type: ignore[arg-type]
        direction=direction,  # type: ignore[arg-type]
        high=high,
        low=low,
        start_bar_index=start,
        end_bar_index=end,
        id=f"{level}:{start}->{end}",
        level=level,
    )


def _make_segment(level: str, strokes: list[Stroke], direction: str) -> Segment:
    return Segment(
        strokes=strokes,
        direction=direction,  # type: ignore[arg-type]
        start_index=strokes[0].start_bar_index,
        end_index=strokes[-1].end_bar_index,
        id=f"{level}:segment:{strokes[0].start_bar_index}->{strokes[-1].end_bar_index}",
        level=level,
        pens=list(strokes),
    )


def test_interval_nesting_detects_time_cover() -> None:
    parent_strokes = [_make_stroke("30m", 0, 10, "up", 11.0, 9.0)]
    parent = _make_segment("30m", parent_strokes, "up")

    child1 = _make_segment("5m", [_make_stroke("5m", 1, 4, "up", 10.5, 9.3)], "up")
    child2 = _make_segment("5m", [_make_stroke("5m", 4, 8, "down", 10.4, 9.2)], "down")

    stats = interval_nesting_for_segment(parent, [child1, child2])
    assert stats["time_cover_count"] == 2
    assert stats["price_partial_nesting"] in {True, False}


def test_build_multilevel_mapping_links_children() -> None:
    high_strokes = [_make_stroke("30m", 0, 10, "up", 11.0, 9.0)]
    low_strokes = [
        _make_stroke("5m", 0, 4, "up", 10.5, 9.5),
        _make_stroke("5m", 4, 8, "down", 10.4, 9.3),
    ]
    high_segments = [_make_segment("30m", high_strokes, "up")]
    low_segments = [_make_segment("5m", [low_strokes[0]], "up"), _make_segment("5m", [low_strokes[1]], "down")]

    mapping = build_multilevel_mapping(
        low_level="5m",
        high_level="30m",
        low_strokes=low_strokes,
        high_strokes=high_strokes,
        low_segments=low_segments,
        high_segments=high_segments,
    )
    assert mapping.segment_map
    parent_id = high_segments[0].id
    assert parent_id in mapping.segment_map
    assert len(mapping.segment_map[parent_id]) == 2


def test_analyze_relation_matrix_reports_resonance() -> None:
    stroke_high = _make_stroke("30m", 0, 10, "up", 11.0, 9.0)
    seg_high = _make_segment("30m", [stroke_high], "up")
    trend_high = Trend(direction="up", segments=[seg_high], start_index=0, end_index=10, level="30m", id="30m:trend")

    stroke_low = _make_stroke("5m", 0, 4, "up", 10.4, 9.4)
    seg_low = _make_segment("5m", [stroke_low], "up")
    trend_low = Trend(direction="up", segments=[seg_low], start_index=0, end_index=4, level="5m", id="5m:trend")

    high_state = StructureLevelState(level="30m", strokes={stroke_high.id: stroke_high}, segments={seg_high.id: seg_high}, trends={trend_high.id: trend_high}, active_trend_id=trend_high.id)
    low_state = StructureLevelState(level="5m", strokes={stroke_low.id: stroke_low}, segments={seg_low.id: seg_low}, trends={trend_low.id: trend_low}, active_trend_id=trend_low.id)

    matrix = analyze_relation_matrix({"30m": high_state, "5m": low_state}, ["30m", "5m"])
    assert matrix["resonance"] is True
    assert matrix["dominant_direction"] == "up"
