from typing import Dict, List, Optional, Tuple

from chanlun_quant.types import (
    MultiLevelMapping,
    Segment,
    Stroke,
    StructureLevelState,
    Trend,
)


def _resolve_index_range(start_value: Optional[int], end_value: Optional[int]) -> Tuple[int, int]:
    start = start_value or 0
    end = end_value or start
    if start > end:
        start, end = end, start
    return start, end


def _ensure_stroke_id(stroke: Stroke) -> str:
    if not stroke.id:
        level = stroke.level or "lvl"
        stroke.id = f"{level}:stroke:{stroke.start_bar_index}-{stroke.end_bar_index}"
    return stroke.id


def _ensure_segment_id(segment: Segment) -> str:
    if not segment.id:
        level = segment.level or "lvl"
        segment.id = f"{level}:segment:{segment.start_index}-{segment.end_index}"
    return segment.id


def _ensure_trend_id(trend: Trend) -> str:
    if not trend.id:
        level = trend.level or "lvl"
        trend.id = f"{level}:trend:{trend.start_index}-{trend.end_index}"
    return trend.id


def _in_time_range(child_start: int, child_end: int, parent_start: int, parent_end: int) -> bool:
    """判断子结构时间是否落在父结构时间区间内（闭区间）。"""
    if child_start > child_end:
        child_start, child_end = child_end, child_start
    if parent_start > parent_end:
        parent_start, parent_end = parent_end, parent_start
    return (child_start >= parent_start) and (child_end <= parent_end)


def map_strokes_low_to_high(low: List[Stroke], high: List[Stroke]) -> Dict[str, List[str]]:
    """
    将低级别Stroke映射到时间区间内的高级别Stroke，设置：
    - child.high_level_parent = parent_stroke
    - parent.lower_level_children.append(child)
    NOTE: 就地修改对象，不返回。
    """
    mapping: Dict[str, List[str]] = {}
    high_sorted = sorted(high, key=lambda s: _resolve_index_range(s.start_bar_index, s.end_bar_index))
    for child in low:
        # 先清理旧引用，避免重复映射
        child.high_level_parent = None
    for parent in high_sorted:
        parent.lower_level_children = []
        parent.metadata["child_stroke_ids"] = []

    for child in low:
        child_id = _ensure_stroke_id(child)
        c_start, c_end = _resolve_index_range(child.start_bar_index, child.end_bar_index)
        for parent in high_sorted:
            p_start, p_end = _resolve_index_range(parent.start_bar_index, parent.end_bar_index)
            if _in_time_range(c_start, c_end, p_start, p_end):
                parent_id = _ensure_stroke_id(parent)
                child.high_level_parent = parent
                parent.lower_level_children.append(child)
                parent.metadata.setdefault("child_stroke_ids", [])
                if child_id not in parent.metadata["child_stroke_ids"]:
                    parent.metadata["child_stroke_ids"].append(child_id)
                mapping.setdefault(parent_id, []).append(child_id)
                break  # 一对一映射到第一个匹配的父级
    return mapping


def map_segments_low_to_high(low: List[Segment], high: List[Segment]) -> Dict[str, List[str]]:
    """
    将低级别Segment映射到时间区间内的高级别Segment。
    返回字典 child_idx -> parent_idx（在 high 列表中的位置索引）。
    NOTE: 不改变Segment对象本身（可在上层按需写回 parent/child）。
    """
    mapping: Dict[str, List[str]] = {}
    indexed_high = list(enumerate(high))
    high_sorted = sorted(indexed_high, key=lambda kv: _resolve_index_range(kv[1].start_index, kv[1].end_index))
    for idx, child in enumerate(low):
        child.parent_segment = None
        child.parent_segment_id = None
    for _, parent in high_sorted:
        parent.child_segments = []
        parent.metadata["child_segment_ids"] = []

    for idx, child in enumerate(low):
        child_id = _ensure_segment_id(child)
        c_start, c_end = _resolve_index_range(child.start_index, child.end_index)
        for parent_idx, parent in high_sorted:
            p_start, p_end = _resolve_index_range(parent.start_index, parent.end_index)
            if _in_time_range(c_start, c_end, p_start, p_end):
                parent_id = _ensure_segment_id(parent)
                mapping.setdefault(parent_id, []).append(child_id)
                child.parent_segment_id = parent_id
                child.parent_segment = parent
                if child not in parent.child_segments:
                    parent.child_segments.append(child)
                parent.metadata.setdefault("child_segment_ids", [])
                if child_id not in parent.metadata["child_segment_ids"]:
                    parent.metadata["child_segment_ids"].append(child_id)
                break
    return mapping


def interval_nesting_for_segment(high_seg: Segment, low_segs: List[Segment]) -> Dict[str, float | bool | int]:
    """计算高级别Segment在低级别Segment中的嵌套情况。"""
    hs, he = _resolve_index_range(high_seg.start_index, high_seg.end_index)
    h_low, h_high = _price_range_of_segment(high_seg)
    time_children: List[Segment] = []
    for seg in low_segs:
        cs, ce = _resolve_index_range(seg.start_index, seg.end_index)
        if _in_time_range(cs, ce, hs, he):
            time_children.append(seg)
    if not time_children:
        return {"time_cover_count": 0, "price_full_nesting": False, "price_partial_nesting": False}

    full = True
    partial = False
    for child in time_children:
        if not _in_time_range(child.start_index, child.end_index, hs, he):
            full = False
            break
    if not full:
        for child in time_children:
            if _in_time_range(child.start_index, child.end_index, hs, he):
                partial = True
                break

    return {
        "time_cover_count": len(time_children),
        "price_full_nesting": full,
        "price_partial_nesting": partial,
    }


def map_trends_low_to_high(low: Optional[List[Trend]], high: Optional[List[Trend]]) -> Dict[str, List[str]]:
    if not low or not high:
        return {}
    mapping: Dict[str, List[str]] = {}
    for parent in high:
        parent.child_trend_ids = []
        parent.metadata.setdefault("child_trend_ids", [])
    for child in low:
        child.parent_trend_id = None
    high_sorted = sorted(high, key=lambda t: _resolve_index_range(t.start_index, t.end_index))
    for child in low:
        child_id = _ensure_trend_id(child)
        c_start, c_end = _resolve_index_range(child.start_index, child.end_index)
        for parent in high_sorted:
            p_start, p_end = _resolve_index_range(parent.start_index, parent.end_index)
            if _in_time_range(c_start, c_end, p_start, p_end):
                parent_id = _ensure_trend_id(parent)
                child.parent_trend_id = parent_id
                mapping.setdefault(parent_id, []).append(child_id)
                if child_id not in parent.child_trend_ids:
                    parent.child_trend_ids.append(child_id)
                parent.metadata.setdefault("child_trend_ids", [])
                if child_id not in parent.metadata["child_trend_ids"]:
                    parent.metadata["child_trend_ids"].append(child_id)
                break
    return mapping


def build_multilevel_mapping(
    low_level: str,
    high_level: str,
    low_strokes: List[Stroke],
    high_strokes: List[Stroke],
    low_segments: List[Segment],
    high_segments: List[Segment],
    low_trends: Optional[List[Trend]] = None,
    high_trends: Optional[List[Trend]] = None,
) -> MultiLevelMapping:
    """
    综合映射结果，包含笔、段映射与区间套指标。
    """
    pen_map = map_strokes_low_to_high(low_strokes, high_strokes)
    segment_map = map_segments_low_to_high(low_segments, high_segments)
    trend_map = map_trends_low_to_high(low_trends, high_trends)

    nesting_info: Dict[str, Dict[str, object]] = {}
    for seg in high_segments:
        seg_id = _ensure_segment_id(seg)
        stats = interval_nesting_for_segment(seg, low_segments)
        seg.metadata.setdefault("nesting", stats)
        nesting_info[seg_id] = stats

    multilevel = MultiLevelMapping(
        higher_level=high_level,
        lower_level=low_level,
        pen_map=pen_map,
        segment_map=segment_map,
        trend_map=trend_map,
        metadata={"segment_nesting": nesting_info},
    )
    return multilevel


def _direction_to_sign(direction: Optional[str]) -> int:
    if not direction:
        return 0
    direction_lower = direction.lower()
    if direction_lower == "up":
        return 1
    if direction_lower == "down":
        return -1
    return 0


def _signal_bias(signals: List["Signal"]) -> str:
    if not signals:
        return "neutral"
    has_buy = any(sig.type.startswith("BUY") for sig in signals)
    has_sell = any(sig.type.startswith("SELL") for sig in signals)
    if has_buy and has_sell:
        return "mixed"
    if has_buy:
        return "buy"
    if has_sell:
        return "sell"
    return "neutral"


def analyze_relation_matrix(
    level_states: Dict[str, StructureLevelState],
    level_order: Optional[List[str]] = None,
) -> Dict[str, object]:
    """计算多级别走势之间的共振/对冲/错位矩阵与摘要。"""

    if not level_states:
        return {
            "levels": [],
            "direction_vector": {},
            "signal_bias": {},
            "matrix": [],
            "resonance": False,
            "hedge": False,
            "dislocation": True,
            "dominant_direction": "flat",
            "dominant_level": None,
            "score": 0.0,
            "summary": "暂无结构信息。",
        }

    order = level_order or list(level_states.keys())
    direction_vector: Dict[str, int] = {}
    signal_bias: Dict[str, str] = {}
    active_levels: List[str] = []

    for level in order:
        state = level_states.get(level)
        direction = 0
        if state:
            signal_bias[level] = _signal_bias(state.signals)
            trend: Optional[Trend] = None
            if state.active_trend_id and state.active_trend_id in state.trends:
                trend = state.trends[state.active_trend_id]
            elif state.trends:
                trend = next(iter(state.trends.values()))
            if trend:
                direction = _direction_to_sign(trend.direction)
        else:
            signal_bias[level] = "neutral"
        direction_vector[level] = direction
        if direction != 0:
            active_levels.append(level)

    positives = [lvl for lvl, d in direction_vector.items() if d > 0]
    negatives = [lvl for lvl, d in direction_vector.items() if d < 0]
    flats = [lvl for lvl, d in direction_vector.items() if d == 0]

    resonance = bool(active_levels) and len(positives) == len(active_levels)
    resonance_down = bool(active_levels) and len(negatives) == len(active_levels)
    resonance = resonance or resonance_down
    hedge = len(positives) > 0 and len(negatives) > 0
    dislocation = len(flats) > 0 or (not resonance and not hedge)

    direction_sum = sum(direction_vector.values())
    magnitude_sum = sum(abs(val) for val in direction_vector.values()) or 1.0
    score = abs(direction_sum) / magnitude_sum
    dominant_direction = "flat"
    if direction_sum > 0:
        dominant_direction = "up"
    elif direction_sum < 0:
        dominant_direction = "down"

    dominant_level = None
    if dominant_direction == "up" and positives:
        dominant_level = positives[0]
    elif dominant_direction == "down" and negatives:
        dominant_level = negatives[0]

    matrix: List[Dict[str, object]] = []
    relation_mapper = {
        (1, 1): "resonance",
        (-1, -1): "resonance",
        (1, -1): "hedge",
        (-1, 1): "hedge",
    }
    for idx, high_level in enumerate(order):
        high_dir = direction_vector.get(high_level, 0)
        for low_level in order[idx + 1 :]:
            low_dir = direction_vector.get(low_level, 0)
            relation = relation_mapper.get((high_dir, low_dir), "dislocation")
            matrix.append(
                {
                    "higher": high_level,
                    "lower": low_level,
                    "relation": relation,
                    "higher_dir": high_dir,
                    "lower_dir": low_dir,
                }
            )

    if resonance:
        summary = f"{'、'.join(active_levels)} 多级别同向共振，方向偏{dominant_direction}。"
    elif hedge:
        summary = (
            f"{'、'.join(positives)} 与 {'、'.join(negatives)} 方向对冲，行情节奏分化，需谨慎。"
        )
    else:
        summary = "部分级别缺乏明确趋势，节奏错位，等待结构同步。"
        if flats:
            summary += f"（无明显趋势级别：{'、'.join(flats)}）"

    return {
        "levels": order,
        "direction_vector": direction_vector,
        "signal_bias": signal_bias,
        "matrix": matrix,
        "resonance": resonance,
        "hedge": hedge,
        "dislocation": dislocation,
        "dominant_direction": dominant_direction,
        "dominant_level": dominant_level,
        "score": score,
        "summary": summary,
        "positives": positives,
        "negatives": negatives,
        "flats": flats,
    }


def _price_range_of_segment(segment: Segment) -> Tuple[float, float]:
    highs = [stroke.high for stroke in segment.strokes]
    lows = [stroke.low for stroke in segment.strokes]
    return (min(lows) if lows else 0.0, max(highs) if highs else 0.0)