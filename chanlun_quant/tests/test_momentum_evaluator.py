from chanlun_quant.core.momentum import MomentumEvaluator
from chanlun_quant.types import Fractal, Segment, Stroke


def make_stroke(direction: str, start_idx: int, end_idx: int, high: float, low: float) -> Stroke:
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
    return Stroke(
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


def make_segment(direction: str, start_idx: int, end_idx: int, high: float, low: float) -> Segment:
    stroke = make_stroke(direction, start_idx, end_idx, high, low)
    return Segment(
        strokes=[stroke],
        direction=direction,
        start_index=start_idx,
        end_index=end_idx,
        level="5m",
        pens=[stroke],
    )


def test_momentum_segment_metrics() -> None:
    closes = [float(i) for i in range(1, 21)]
    evaluator = MomentumEvaluator(closes)
    seg = make_segment("up", 5, 10, 16.0, 12.0)
    metrics = evaluator.segment_metrics(seg)
    assert "area" in metrics and "density" in metrics
    assert metrics["length"] == 5.0
    assert metrics["high"] == 16.0
    assert metrics["low"] == 12.0


def test_momentum_compare_segments_detects_ratio() -> None:
    closes = [float(i) for i in range(1, 30)]
    evaluator = MomentumEvaluator(closes)
    seg_a = make_segment("up", 5, 14, 20.0, 11.0)
    seg_c = make_segment("up", 14, 23, 24.0, 16.0)
    result = evaluator.compare_segments(seg_a, seg_c)
    assert "area_ratio" in result
    assert result["area_ratio"] >= 0.0


def test_momentum_state_uses_child_segments() -> None:
    closes = [float(i) for i in range(1, 40)]
    evaluator = MomentumEvaluator(closes)
    base = make_segment("up", 10, 18, 25.0, 15.0)
    seg = make_segment("up", 18, 26, 30.0, 20.0)
    seg.child_segments.append(base)
    state = evaluator.momentum_state(seg)
    assert set(state.keys()) == {"direction", "bias", "strength", "tail_span", "divergence"}
    assert "has_divergence" in state["divergence"]


def test_momentum_to_llm_context_contains_snapshot() -> None:
    closes = [float(i) for i in range(1, 25)]
    evaluator = MomentumEvaluator(closes)
    seg = make_segment("down", 6, 15, 18.0, 11.0)
    context = evaluator.to_llm_context(seg)
    assert "segment_direction" in context
    assert "macd_density" in context
    assert "ema_trend" in context
