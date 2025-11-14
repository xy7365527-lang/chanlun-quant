from chanlun_quant.analysis.post_divergence import analyze_post_divergence
from chanlun_quant.types import Central, Fractal, Segment, Stroke


def make_segment(direction: str, start_idx: int, end_idx: int, high: float, low: float) -> Segment:
    start_fractal = Fractal(
        type="bottom" if direction == "up" else "top",
        index=start_idx,
        price=low if direction == "up" else high,
        bar_index=start_idx,
        level="5m",
    )
    end_fractal = Fractal(
        type="top" if direction == "up" else "bottom",
        index=end_idx,
        price=high if direction == "up" else low,
        bar_index=end_idx,
        level="5m",
    )
    stroke = Stroke(
        start_fractal=start_fractal,
        end_fractal=end_fractal,
        direction=direction,
        high=high,
        low=low,
        start_bar_index=start_idx,
        end_bar_index=end_idx,
        id=f"{start_idx}->{end_idx}",
        level="5m",
    )
    return Segment(
        strokes=[stroke],
        direction=direction,
        start_index=start_idx,
        end_index=end_idx,
        level="5m",
        pens=[stroke],
    )


def test_post_divergence_identifies_consolidation() -> None:
    segments = [
        make_segment("up", 0, 10, 110.0, 100.0),
        make_segment("down", 10, 20, 109.5, 100.5),
        make_segment("up", 20, 30, 110.2, 100.8),
    ]
    outcome = analyze_post_divergence(None, segments, overlap_threshold=0.6)
    assert outcome.classification == "consolidation"
    assert outcome.overlap_rate >= 0.6


def test_post_divergence_detects_new_trend_after_breakout() -> None:
    central = Central(level="5m", zg=110.0, zd=100.0, start_index=0, end_index=50)
    segments = [
        make_segment("up", 0, 10, 111.0, 101.5),
        make_segment("up", 10, 20, 115.0, 104.0),
        make_segment("down", 20, 30, 113.5, 105.0),
    ]
    outcome = analyze_post_divergence(central, segments)
    assert outcome.classification == "new_trend"
    assert outcome.left_central is True
    assert outcome.new_trend_direction == "up"


def test_post_divergence_marks_central_extension_when_inside_range() -> None:
    central = Central(level="5m", zg=110.0, zd=100.0, start_index=0, end_index=50)
    segments = [
        make_segment("down", 0, 10, 109.0, 101.5),
        make_segment("up", 10, 20, 108.5, 100.8),
        make_segment("down", 20, 30, 109.2, 101.0),
    ]
    outcome = analyze_post_divergence(central, segments, overlap_threshold=0.8)
    assert outcome.classification == "central_extension"
    assert outcome.left_central is False
