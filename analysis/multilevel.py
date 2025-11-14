from __future__ import annotations

from typing import Dict, List, Tuple

from chanlun_quant.types import Segment, Stroke


def _in_time_range(child_start: int, child_end: int, parent_start: int, parent_end: int) -> bool:
    """判断子结构时间是否落在父结构时间区间内（闭区间）。"""
    if child_start > child_end:
        child_start, child_end = child_end, child_start
    if parent_start > parent_end:
        parent_start, parent_end = parent_end, parent_start
    return (child_start >= parent_start) and (child_end <= parent_end)


def _price_range_of_segment(seg: Segment) -> Tuple[float, float]:
    """返回段的(低,高)价格区间，基于内部笔的low/high。"""
    if not seg.strokes:
        return 0.0, 0.0
    low = min(st.low for st in seg.strokes)
    high = max(st.high for st in seg.strokes)
    if low > high:
        low, high = high, low
    return low, high


def map_strokes_low_to_high(low: List[Stroke], high: List[Stroke]) -> None:
    """
    将低级别Stroke映射到时间区间内的高级别Stroke，设置：
    - child.high_level_parent = parent_stroke
    - parent.lower_level_children.append(child)
    NOTE: 就地修改对象，不返回。
    """
    high_sorted = sorted(high, key=lambda s: (s.start_bar_index, s.end_bar_index))
    for child in low:
        # 先清理旧引用，避免重复映射
        child.high_level_parent = None
        for parent in high_sorted:
            if _in_time_range(child.start_bar_index, child.end_bar_index, parent.start_bar_index, parent.end_bar_index):
                child.high_level_parent = parent
                parent.lower_level_children.append(child)
                break  # 一对一映射到第一个匹配的父级


def map_segments_low_to_high(low: List[Segment], high: List[Segment]) -> Dict[int, int]:
    """
    将低级别Segment映射到时间区间内的高级别Segment。
    返回字典 child_idx -> parent_idx（在 high 列表中的位置索引）。
    NOTE: 不改变Segment对象本身（可在上层按需写回 parent/child）。
    """
    mapping: Dict[int, int] = {}
    high_sorted = sorted(enumerate(high), key=lambda kv: (kv[1].start_index, kv[1].end_index))
    for idx, child in enumerate(low):
        child.parent_segment = None
        for parent_idx, parent in high_sorted:
            if _in_time_range(child.start_index, child.end_index, parent.start_index, parent.end_index):
                mapping[idx] = parent_idx
                child.parent_segment = parent
                parent.child_segments.append(child)
                break
    return mapping


def interval_nesting_for_segment(high_seg: Segment, low_segs: List[Segment]) -> Dict[str, float | bool | int]:
    """
    计算高段与所有落入其时间区间的低段之间的“区间套”指标。
    """
    hs, he = high_seg.start_index, high_seg.end_index
    h_low, h_high = _price_range_of_segment(high_seg)
    time_children: List[Segment] = []
    for seg in low_segs:
        if _in_time_range(seg.start_index, seg.end_index, hs, he):
            time_children.append(seg)
    if not time_children:
        return {"time_cover_count": 0, "price_full_nesting": False, "price_partial_nesting": False}

    full = True
    partial = False
    for ch in time_children:
        c_low, c_high = _price_range_of_segment(ch)
        if not (c_low >= h_low and c_high <= h_high):
            full = False
            partial = True
    return {
        "time_cover_count": len(time_children),
        "price_full_nesting": full,
        "price_partial_nesting": partial,
    }


def build_multilevel_mapping(
    low_level: str,
    high_level: str,
    low_strokes: List[Stroke],
    high_strokes: List[Stroke],
    low_segments: List[Segment],
    high_segments: List[Segment],
) -> Dict[str, object]:
    """
    综合映射结果，包含笔、段映射与区间套指标。
    """
    for hs in high_strokes:
        hs.lower_level_children = []
    map_strokes_low_to_high(low_strokes, high_strokes)

    for hg in high_segments:
        hg.child_segments = []
    mapping = map_segments_low_to_high(low_segments, high_segments)

    nesting: Dict[int, Dict[str, object]] = {}
    for idx, seg in enumerate(high_segments):
        nesting[idx] = interval_nesting_for_segment(seg, low_segments)

    return {
        "low_level": low_level,
        "high_level": high_level,
        "stroke_mapping_done": True,
        "segment_mapping": mapping,
        "nesting": nesting,
    }
