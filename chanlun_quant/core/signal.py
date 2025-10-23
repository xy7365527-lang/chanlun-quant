from __future__ import annotations

from typing import Dict, List, Optional

from chanlun_quant.core import momentum
from chanlun_quant.types import Central, Segment, Signal


def _segment_high(segment: Segment) -> float:
    return max(stroke.high for stroke in segment.strokes)


def _segment_low(segment: Segment) -> float:
    return min(stroke.low for stroke in segment.strokes)


def _segment_level(segment: Segment) -> Optional[str]:
    if segment.level:
        return segment.level
    if segment.strokes:
        return segment.strokes[-1].level
    return None


def _make_signal(signal_type: str, segment: Segment, price: float, info: Dict[str, float] | None = None) -> Signal:
    payload = dict(info or {})
    payload.setdefault("segment_start", float(segment.start_index))
    payload.setdefault("segment_end", float(segment.end_index))
    return Signal(
        type=signal_type,
        price=price,
        index=segment.end_index,
        level=_segment_level(segment),
        extra=payload,
    )


def detect_signals(
    segments: List[Segment],
    centrals: List[Central],
    macd: Dict[str, List[float]],
    cfg,
) -> List[Signal]:
    """Detect Chanlun class-1/2/3 signals from high-level structures."""
    if not segments:
        return []

    sorted_segments = sorted(segments, key=lambda seg: (seg.start_index, seg.end_index))
    signals: List[Signal] = []
    last_by_dir: Dict[str, Segment] = {}
    threshold = getattr(cfg, "divergence_threshold", 0.8)
    area_mode = getattr(cfg, "macd_area_mode", "hist")

    for idx, seg in enumerate(sorted_segments):
        previous_same = last_by_dir.get(seg.direction)
        if previous_same is not None:
            if momentum.is_trend_divergent(previous_same, seg, macd, threshold=threshold, area_mode=area_mode):
                if seg.direction == "down":
                    price = _segment_low(seg)
                    signals.append(_make_signal("BUY1", seg, price, info={"class": 1.0, "area_mode": area_mode}))
                else:
                    price = _segment_high(seg)
                    signals.append(_make_signal("SELL1", seg, price, info={"class": 1.0, "area_mode": area_mode}))
        last_by_dir[seg.direction] = seg

        if seg.direction == "down" and idx >= 2:
            prev_up = sorted_segments[idx - 1]
            prev_down = sorted_segments[idx - 2]
            if prev_down.direction == "down" and prev_up.direction == "up":
                if _segment_low(seg) >= _segment_low(prev_down):
                    signals.append(_make_signal("BUY2", seg, _segment_low(seg), info={"class": 2.0}))

        if seg.direction == "up" and idx >= 2:
            prev_down = sorted_segments[idx - 1]
            prev_up = sorted_segments[idx - 2]
            if prev_up.direction == "up" and prev_down.direction == "down":
                if _segment_high(seg) <= _segment_high(prev_up):
                    signals.append(_make_signal("SELL2", seg, _segment_high(seg), info={"class": 2.0}))

    if centrals:
        _detect_class3(sorted_segments, centrals, signals)

    return signals


def _detect_class3(segments: List[Segment], centrals: List[Central], out: List[Signal]) -> None:
    if not segments:
        return
    for central in centrals:
        start_pos = 0
        if central.stroke_indices:
            start_pos = max(central.stroke_indices) + 1
        post_segments = segments[start_pos:]
        post_segments = [seg for seg in post_segments if seg.start_index >= central.end_index]
        if not post_segments:
            continue
        breakout = post_segments[0]
        if breakout.direction == "up":
            pullback = next((seg for seg in post_segments[1:] if seg.direction == "down"), None)
            if pullback and _segment_low(pullback) > central.zd:
                out.append(_make_signal("BUY3", pullback, _segment_low(pullback), info={"class": 3.0, "central_zd": central.zd}))
        elif breakout.direction == "down":
            pullback = next((seg for seg in post_segments[1:] if seg.direction == "up"), None)
            if pullback and _segment_high(pullback) < central.zg:
                out.append(_make_signal("SELL3", pullback, _segment_high(pullback), info={"class": 3.0, "central_zg": central.zg}))
