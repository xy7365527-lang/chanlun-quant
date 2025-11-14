from __future__ import annotations

from typing import List, Optional

from chanlun_quant.types import Direction, Segment, Stroke


def _overlap(a_low: float, a_high: float, b_low: float, b_high: float, tol: float = 0.0) -> bool:
    """
    判断两区间是否有重叠（含端点），允许 tol 容差。
    有重叠 → True；无重叠（存在“缺口”）→ False。
    """
    if a_low > a_high:
        a_low, a_high = a_high, a_low
    if b_low > b_high:
        b_low, b_high = b_high, b_low
    return not (a_low > b_high + tol or b_low > a_high + tol)


def _is_opposite(direction: Direction, stroke: Stroke) -> bool:
    return (direction == "up" and stroke.direction == "down") or (
        direction == "down" and stroke.direction == "up"
    )


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
    将笔序列聚合成线段，基于特征序列（反向笔序列）的缺口规则判段。
    """
    res: List[Segment] = []
    if not strokes:
        return res

    ordered = sorted(strokes, key=lambda s: (s.start_bar_index, s.end_bar_index, s.id or ""))
    current: List[Stroke] = []
    opposite_seq: List[Stroke] = []
    seg_direction: Optional[Direction] = None
    start_index: Optional[int] = None

    def flush(end_confirmed: bool) -> None:
        nonlocal current, opposite_seq, seg_direction, start_index
        if not current:
            return
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
        res.append(segment)
        current = []
        opposite_seq = []
        seg_direction = None
        start_index = None

    for stroke in ordered:
        if not current:
            current.append(stroke)
            seg_direction = stroke.direction
            start_index = stroke.start_bar_index
            opposite_seq = []
            continue

        if stroke.direction == seg_direction:
            current.append(stroke)
            continue

        current.append(stroke)
        opposite_seq.append(stroke)

        if len(opposite_seq) >= 2:
            previous = opposite_seq[-2]
            latest = opposite_seq[-1]
            has_overlap = _overlap(previous.low, previous.high, latest.low, latest.high, tol=gap_tolerance)
            if has_overlap:
                carry = current.pop()
                opposite_seq.pop()
                flush(end_confirmed=True)
                current.append(carry)
                seg_direction = carry.direction
                start_index = carry.start_bar_index
                opposite_seq = []
            else:
                if not strict_feature_sequence:
                    carry = current.pop()
                    opposite_seq.pop()
                    flush(end_confirmed=False)
                    current.append(carry)
                    seg_direction = carry.direction
                    start_index = carry.start_bar_index
                    opposite_seq = []

    if current:
        flush(end_confirmed=False)

    return res
