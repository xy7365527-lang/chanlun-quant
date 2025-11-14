from chanlun_quant.core.segment import build_segments
from chanlun_quant.types import Fractal, Stroke


def mk_stroke(start_idx: int, end_idx: int, direction: str, high: float, low: float, level: str = "5m") -> Stroke:
    start_type = "bottom" if direction == "up" else "top"
    end_type = "top" if direction == "up" else "bottom"
    start_price = low if direction == "up" else high
    end_price = high if direction == "up" else low
    start_fractal = Fractal(type=start_type, index=start_idx, price=start_price, bar_index=start_idx, level=level)
    end_fractal = Fractal(type=end_type, index=end_idx, price=end_price, bar_index=end_idx, level=level)
    return Stroke(
        start_fractal=start_fractal,
        end_fractal=end_fractal,
        direction=direction,
        high=high,
        low=low,
        start_bar_index=start_idx,
        end_bar_index=end_idx,
        id=f"{start_idx}->{end_idx}",
        level=level,
    )


def test_segment_feature_sequence_standard_end() -> None:
    strokes = [
        mk_stroke(0, 1, "up", 11.0, 9.0),
        mk_stroke(1, 2, "down", 12.0, 9.1),
        mk_stroke(2, 3, "up", 12.6, 10.4),
        mk_stroke(3, 4, "down", 13.4, 10.8),
        mk_stroke(4, 5, "up", 14.0, 11.6),
        mk_stroke(5, 6, "down", 11.5, 9.7),
    ]
    segments = build_segments(strokes, strict_feature_sequence=True, gap_tolerance=0.0)
    assert segments
    first = segments[0]
    assert first.direction == "up"
    assert first.end_confirmed is True
    assert first.feature_fractal is not None
    assert first.feature_fractal.type == "top"
    assert first.feature_fractal.has_gap is False
    assert first.pending_confirmation is False
    assert len(first.feature_sequence) >= 3


def test_segment_gap_pending_without_confirmation() -> None:
    strokes = [
        mk_stroke(0, 1, "up", 11.0, 9.0),
        mk_stroke(1, 2, "down", 12.0, 9.2),
        mk_stroke(2, 3, "up", 12.5, 10.3),
        mk_stroke(3, 4, "down", 15.0, 13.5),  # 构造缺口（第二笔高低均在第一笔之上）
        mk_stroke(4, 5, "up", 13.8, 11.8),
        mk_stroke(5, 6, "down", 11.2, 9.5),
    ]
    segments = build_segments(strokes, strict_feature_sequence=True, gap_tolerance=0.0)
    assert segments
    first = segments[0]
    assert first.feature_fractal is not None
    assert first.feature_fractal.has_gap is True
    assert first.end_confirmed is False
    assert first.pending_confirmation is True


def test_segment_gap_confirmed_after_follow_up_fractal() -> None:
    base = [
        mk_stroke(0, 1, "up", 11.0, 9.0),
        mk_stroke(1, 2, "down", 12.0, 9.2),
        mk_stroke(2, 3, "up", 12.5, 10.3),
        mk_stroke(3, 4, "down", 15.0, 13.5),
        mk_stroke(4, 5, "up", 13.8, 11.8),
        mk_stroke(5, 6, "down", 11.2, 9.5),
    ]
    follow_up = [
        mk_stroke(6, 7, "up", 11.1, 9.7),
        mk_stroke(7, 8, "down", 10.8, 8.9),
        mk_stroke(8, 9, "up", 10.3, 8.4),
        mk_stroke(9, 10, "down", 10.0, 8.1),
        mk_stroke(10, 11, "up", 11.2, 9.2),
    ]
    segments = build_segments(base + follow_up, strict_feature_sequence=True, gap_tolerance=0.0)
    assert segments
    first = segments[0]
    assert first.feature_fractal is not None
    assert first.feature_fractal.has_gap is True
    assert first.end_confirmed is True
    assert first.pending_confirmation is False
