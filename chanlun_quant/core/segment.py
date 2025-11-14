from __future__ import annotations

from typing import List, Optional

from chanlun_quant.features.feature_sequence import FeatureSequenceBuilder, FeatureSequenceState
from chanlun_quant.types import Direction, Segment, Stroke


def _segment_end_index(current_segment_strokes: List[Stroke], seg_direction: Direction) -> int:
    for st in reversed(current_segment_strokes):
        if st.direction == seg_direction:
            return st.end_bar_index
    return current_segment_strokes[-1].end_bar_index


def build_segments(
    strokes: List[Stroke],
    strict_feature_sequence: bool = True,
    gap_tolerance: float = 0.0,
) -> List[Segment]:
    """
    将笔序列聚合成线段：
    - 使用特征序列（反向笔）构造线段终结分型；
    - 缺口分型需等待下一段确认（严格模式）。
    """
    res: List[Segment] = []
    if not strokes:
        return res

    ordered = sorted(strokes, key=lambda s: (s.start_bar_index, s.end_bar_index, s.id or ""))
    current: List[Stroke] = []
    seg_direction: Optional[Direction] = None
    start_index: Optional[int] = None
    feature_builder = FeatureSequenceBuilder(gap_tolerance=gap_tolerance)
    pending_gap_segment: Optional[Segment] = None

    def flush(
        end_confirmed: bool,
        feature_state: Optional[FeatureSequenceState] = None,
        pending_flag: bool = False,
    ) -> Optional[Segment]:
        nonlocal current, seg_direction, start_index
        if not current:
            return None
        direction = seg_direction if seg_direction is not None else current[0].direction
        end_index = _segment_end_index(current, direction)
        level = current[0].level
        segment = Segment(
            strokes=list(current),
            direction=direction,
            start_index=start_index if start_index is not None else current[0].start_bar_index,
            end_index=end_index,
            end_confirmed=end_confirmed,
            level=level,
            pens=list(current),
        )
        if feature_state:
            segment.feature_sequence = list(feature_state.sequence)
            segment.feature_fractal = feature_state.fractal
        else:
            segment.feature_sequence = feature_builder.snapshot()
        segment.pending_confirmation = pending_flag
        res.append(segment)
        current.clear()
        seg_direction = None
        start_index = None
        feature_builder.clear()
        return segment

    for stroke in ordered:
        if not current:
            current.append(stroke)
            seg_direction = stroke.direction
            start_index = stroke.start_bar_index
            feature_builder.reset(seg_direction)
            continue

        if stroke.direction == seg_direction:
            current.append(stroke)
            continue

        current.append(stroke)
        state = feature_builder.append(stroke)
        if not state:
            continue

        if pending_gap_segment is not None:
            pending_gap_segment.end_confirmed = True
            pending_gap_segment.pending_confirmation = False
            pending_gap_segment = None

        carry = current.pop()
        pending_needed = bool(state.fractal.has_gap and strict_feature_sequence)
        end_confirmed = not state.fractal.has_gap or not strict_feature_sequence
        segment = flush(
            end_confirmed=end_confirmed,
            feature_state=state,
            pending_flag=pending_needed,
        )
        current.append(carry)
        seg_direction = carry.direction
        start_index = carry.start_bar_index
        feature_builder.reset(seg_direction)
        if pending_needed and segment is not None:
            pending_gap_segment = segment
        else:
            pending_gap_segment = None

    if current:
        flush(end_confirmed=False)

    return res
