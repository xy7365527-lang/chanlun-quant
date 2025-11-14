from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from chanlun_quant.rsg.schema import PenNode, RSG, SegmentNode, TrendNode
from chanlun_quant.types import Segment, Stroke, StructureState

LEVEL_ORDER = ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]

__all__ = [
    "LEVEL_ORDER",
    "MappingResult",
    "StructureMapper",
    "RelationMatrix",
    "MultiLevelAnalyzer",
]


def _sort_levels(levels: Iterable[str]) -> List[str]:
    def _key(level: str) -> Tuple[int, str]:
        try:
            return (LEVEL_ORDER.index(level), level)
        except ValueError:
            return (len(LEVEL_ORDER), level)

    return sorted(dict.fromkeys(levels), key=_key)


def _segment_price_bounds(segment: SegmentNode, pens: Mapping[str, PenNode]) -> Tuple[float, float]:
    if not segment.pens:
        return segment.macd_eff_price, segment.macd_eff_price
    highs: List[float] = []
    lows: List[float] = []
    for pid in segment.pens:
        pen = pens.get(pid)
        if pen is None:
            continue
        highs.append(pen.high)
        lows.append(pen.low)
    if not highs or not lows:
        return segment.macd_eff_price, segment.macd_eff_price
    return max(highs), min(lows)


@dataclass
class PerParentMetrics:
    time_coverage: float
    price_coverage: float
    child_count: int


@dataclass
class MappingResult:
    high_level: str
    low_level: str
    segment_children: Dict[str, List[str]] = field(default_factory=dict)
    pen_children: Dict[str, List[str]] = field(default_factory=dict)
    per_parent_metrics: Dict[str, PerParentMetrics] = field(default_factory=dict)

    def summary(self) -> Dict[str, Any]:
        metrics = list(self.per_parent_metrics.values())
        if not metrics:
            return {
                "high_level": self.high_level,
                "low_level": self.low_level,
                "avg_time_coverage": 0.0,
                "avg_price_coverage": 0.0,
                "avg_child_count": 0.0,
            }
        avg_time = sum(m.time_coverage for m in metrics) / len(metrics)
        avg_price = sum(m.price_coverage for m in metrics) / len(metrics)
        avg_child = sum(m.child_count for m in metrics) / len(metrics)
        return {
            "high_level": self.high_level,
            "low_level": self.low_level,
            "avg_time_coverage": avg_time,
            "avg_price_coverage": avg_price,
            "avg_child_count": avg_child,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "high_level": self.high_level,
            "low_level": self.low_level,
            "segment_children": dict(self.segment_children),
            "pen_children": dict(self.pen_children),
            "per_parent_metrics": {
                key: {
                    "time_coverage": value.time_coverage,
                    "price_coverage": value.price_coverage,
                    "child_count": value.child_count,
                }
                for key, value in self.per_parent_metrics.items()
            },
            "summary": self.summary(),
        }


class StructureMapper:
    """跨级别结构映射与区间套标注。"""

    def __init__(self, rsg: RSG) -> None:
        self.rsg = rsg

    def _collect_pens(self, level: str) -> List[PenNode]:
        return [pen for pen in self.rsg.pens.values() if getattr(pen, "level", None) == level]

    def _collect_segments(self, level: str) -> List[SegmentNode]:
        return [seg for seg in self.rsg.segments.values() if getattr(seg, "level", None) == level]

    @staticmethod
    def _in_range(child_start: int, child_end: int, parent_start: int, parent_end: int) -> bool:
        if child_start > child_end:
            child_start, child_end = child_end, child_start
        if parent_start > parent_end:
            parent_start, parent_end = parent_end, parent_start
        return child_start >= parent_start and child_end <= parent_end

    def map_level_pair(self, high_level: str, low_level: str) -> MappingResult:
        high_segments = self._collect_segments(high_level)
        low_segments = self._collect_segments(low_level)
        high_pens = self._collect_pens(high_level)
        low_pens = self._collect_pens(low_level)

        segment_children: Dict[str, List[str]] = {seg.id: [] for seg in high_segments}
        per_parent_metrics: Dict[str, PerParentMetrics] = {}
        pen_children: Dict[str, List[str]] = {pen.id: [] for pen in high_pens}

        pen_lookup: Dict[str, PenNode] = {pen.id: pen for pen in self.rsg.pens.values()}

        for child in low_segments:
            for parent in high_segments:
                if self._in_range(child.i0, child.i1, parent.i0, parent.i1):
                    segment_children[parent.id].append(child.id)
                    break

        for child in low_pens:
            for parent in high_pens:
                if self._in_range(child.i0, child.i1, parent.i0, parent.i1):
                    pen_children[parent.id].append(child.id)
                    break

        for parent in high_segments:
            children_ids = segment_children.get(parent.id, [])
            parent_span = max(1, parent.i1 - parent.i0)
            if not children_ids:
                per_parent_metrics[parent.id] = PerParentMetrics(0.0, 0.0, 0)
                continue
            child_time = sum(max(0, self.rsg.segments[child_id].i1 - self.rsg.segments[child_id].i0) for child_id in children_ids)
            time_coverage = child_time / parent_span

            parent_high, parent_low = _segment_price_bounds(parent, pen_lookup)
            if parent_high == parent_low:
                price_coverage = 1.0
            else:
                child_high = max(
                    _segment_price_bounds(self.rsg.segments[child_id], pen_lookup)[0]
                    for child_id in children_ids
                )
                child_low = min(
                    _segment_price_bounds(self.rsg.segments[child_id], pen_lookup)[1]
                    for child_id in children_ids
                )
                price_coverage = min(1.0, max(0.0, (child_high - child_low) / max(1e-9, parent_high - parent_low)))

            per_parent_metrics[parent.id] = PerParentMetrics(
                time_coverage=time_coverage,
                price_coverage=price_coverage,
                child_count=len(children_ids),
            )

        return MappingResult(
            high_level=high_level,
            low_level=low_level,
            segment_children=segment_children,
            pen_children=pen_children,
            per_parent_metrics=per_parent_metrics,
        )


class RelationMatrix:
    """多级别趋势方向矩阵与共振/对冲/错位判断。"""

    def __init__(self, rsg: RSG) -> None:
        self.rsg = rsg

    @staticmethod
    def _direction_to_int(trend_type: str) -> int:
        trend_type = trend_type.lower()
        if trend_type.startswith("up"):
            return 1
        if trend_type.startswith("down"):
            return -1
        return 0

    def _latest_trend(self, level: str) -> Optional[TrendNode]:
        trends = [trend for trend in self.rsg.trends.values() if getattr(trend, "level", None) == level]
        if not trends:
            return None
        trends.sort(key=lambda t: t.id)
        return trends[-1]

    def matrix(self, levels: Sequence[str]) -> Dict[str, Any]:
        directions: Dict[str, int] = {}
        raw_trends: Dict[str, Optional[TrendNode]] = {}
        for level in levels:
            trend = self._latest_trend(level)
            raw_trends[level] = trend
            directions[level] = self._direction_to_int(trend.trend_type) if trend else 0

        pairs: List[Dict[str, Any]] = []
        consensus_score = 0
        for idx in range(len(levels) - 1):
            low = levels[idx]
            high = levels[idx + 1]
            low_dir = directions.get(low, 0)
            high_dir = directions.get(high, 0)
            if low_dir == 0 or high_dir == 0:
                relation = "错位"
                score = 0
            elif low_dir == high_dir:
                relation = "共振"
                score = 1
            else:
                relation = "对冲"
                score = -1
            consensus_score += score
            pairs.append(
                {
                    "low_level": low,
                    "high_level": high,
                    "low_direction": low_dir,
                    "high_direction": high_dir,
                    "relation": relation,
                    "score": score,
                }
            )

        dominant_value = sum(directions.values())
        if dominant_value > 0:
            dominant = "多头"
        elif dominant_value < 0:
            dominant = "空头"
        else:
            dominant = "震荡"

        return {
            "directions": directions,
            "pairs": pairs,
            "dominant": dominant,
            "consensus_score": consensus_score,
            "raw_trends": {
                level: {
                    "trend_type": trend.trend_type if trend else None,
                    "confirmed": trend.confirmed if trend else None,
                }
                for level, trend in raw_trends.items()
            },
        }


class MultiLevelAnalyzer:
    """多级别结构递归分析 + 共振矩阵生成器。"""

    def __init__(self, rsg: RSG) -> None:
        self.rsg = rsg
        self.levels = _sort_levels(rsg.levels or [])
        self.mapper = StructureMapper(rsg)
        self.relations = RelationMatrix(rsg)

    def analyze(
        self,
        levels: Optional[Sequence[str]] = None,
        include_signals: Optional[Mapping[str, Any]] = None,
        include_centrals: Optional[Mapping[str, Any]] = None,
    ) -> StructureState:
        levels = list(levels) if levels else list(self.levels)
        levels = _sort_levels(levels)
        mapping_results: Dict[str, Dict[str, Any]] = {}

        for idx in range(len(levels) - 1):
            low = levels[idx]
            high = levels[idx + 1]
            result = self.mapper.map_level_pair(high_level=high, low_level=low)
            mapping_results[f"{high}->{low}"] = result.to_dict()

        relation_payload = self.relations.matrix(levels)
        trends_summary = relation_payload.pop("raw_trends", {})

        structure_state = StructureState(
            levels=list(levels),
            trends=trends_summary,
            signals=dict(include_signals or {}),
            centrals=dict(include_centrals or {}),
            relations=relation_payload,
            nesting=mapping_results,
            generated_at=datetime.utcnow(),
        )
        structure_state.advice = self._advise(structure_state)
        return structure_state

    @staticmethod
    def _advise(state: StructureState) -> Dict[str, Any]:
        relations = state.relations
        pairs = relations.get("pairs", [])
        if not pairs:
            return {"stance": "观望", "reason": "缺少多级别趋势信息"}

        resonance = all(pair["relation"] == "共振" for pair in pairs if pair["relation"] != "错位")
        any_conflict = any(pair["relation"] == "对冲" for pair in pairs)

        if resonance and not any_conflict:
            stance = "顺势持有"
            reason = "所有级别同向共振"
        elif any_conflict:
            stance = "降低仓位"
            reason = "存在级别对冲信号"
        else:
            stance = "耐心等待"
            reason = "级别方向不一致，趋势未同步"
        return {"stance": stance, "reason": reason}


# ---------------------------------------------------------------------------
# 兼容旧接口：保留笔/线段映射工具函数供已有代码与单元测试使用
# ---------------------------------------------------------------------------


def _in_time_range(child_start: int, child_end: int, parent_start: int, parent_end: int) -> bool:
    if child_start > child_end:
        child_start, child_end = child_end, child_start
    if parent_start > parent_end:
        parent_start, parent_end = parent_end, parent_start
    return (child_start >= parent_start) and (child_end <= parent_end)


def _price_range_of_segment(seg: Segment) -> Tuple[float, float]:
    if not seg.strokes:
        return 0.0, 0.0
    low = min(st.low for st in seg.strokes)
    high = max(st.high for st in seg.strokes)
    if low > high:
        low, high = high, low
    return low, high


def map_strokes_low_to_high(low: List[Stroke], high: List[Stroke]) -> None:
    high_sorted = sorted(high, key=lambda s: (s.start_bar_index, s.end_bar_index))
    for child in low:
        child.high_level_parent = None
        for parent in high_sorted:
            if _in_time_range(child.start_bar_index, child.end_bar_index, parent.start_bar_index, parent.end_bar_index):
                child.high_level_parent = parent
                parent.lower_level_children.append(child)
                break


def map_segments_low_to_high(low: List[Segment], high: List[Segment]) -> Dict[int, int]:
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
