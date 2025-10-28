from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ..rsg.schema import Level, PenNode, RSG, SegmentNode, TrendNode


@dataclass
class SegmentIndex:
    """RSG 的跨级映射/查询索引。"""

    rsg: RSG
    parent: Dict[str, str] = field(init=False, default_factory=dict)
    children: Dict[str, List[str]] = field(init=False, default_factory=dict)
    level_segments: Dict[Level, List[str]] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        for edge in self.rsg.edges:
            parent_id = edge["parent"]
            child_id = edge["child"]
            self.parent[child_id] = parent_id
            self.children.setdefault(parent_id, []).append(child_id)

        for seg in self.rsg.segments.values():
            self.level_segments.setdefault(seg.level, []).append(seg.id)

    # --- 基础访问 ------------------------------------------------------
    def get_segment(self, seg_id: str) -> SegmentNode:
        return self.rsg.segments[seg_id]

    def get_pen(self, pen_id: str) -> PenNode:
        return self.rsg.pens[pen_id]

    def get_trend(self, trend_id: str) -> TrendNode:
        return self.rsg.trends[trend_id]

    # --- 映射查询 ------------------------------------------------------
    def map_to_higher(self, level: Level, elem_id: str) -> Optional[str]:
        """找上一级父元素（若有多级可迭代，此处返回最近一级）。"""
        current = elem_id
        while current in self.parent:
            parent_id = self.parent[current]
            if parent_id in self.rsg.segments or parent_id in self.rsg.trends:
                return parent_id
            current = parent_id
        return None

    def map_to_lower(self, level: Level, elem_id: str) -> List[str]:
        """返回直接子元素集合。"""
        return list(self.children.get(elem_id, []))

    def current_segment(self, level: Level, ts_idx: int) -> Optional[str]:
        """根据时间索引找到该级别内的线段。"""
        candidates = self.level_segments.get(level, [])
        best_id: Optional[str] = None
        for seg_id in candidates:
            seg = self.rsg.segments[seg_id]
            if seg.i0 <= ts_idx <= seg.i1:
                if best_id is None:
                    best_id = seg_id
                else:
                    best_seg = self.rsg.segments[best_id]
                    if (seg.i1 - seg.i0) < (best_seg.i1 - best_seg.i0):
                        best_id = seg_id
        return best_id

    # --- 指标查询 ------------------------------------------------------
    def seg_area_divergence(self, level: Level, seg_id: str) -> bool:
        seg = self.get_segment(seg_id)
        return seg.divergence in ("trend_div", "range_div")

    def mmd_exists(self, node_id: str, kinds: Sequence[str]) -> bool:
        if node_id in self.rsg.segments:
            arr = self.rsg.segments[node_id].mmds
        elif node_id in self.rsg.pens:
            arr = self.rsg.pens[node_id].mmds
        elif node_id in self.rsg.trends:
            arr = self.rsg.trends[node_id].mmds
        else:
            return False
        return any(kind in arr for kind in kinds)

    def near_zhongshu_band(self, seg_id: str, price: float) -> str:
        segment = self.get_segment(seg_id)
        if not segment.zhongshu:
            return "unknown"
        zg = segment.zhongshu.get("zg", float("nan"))
        zd = segment.zhongshu.get("zd", float("nan"))
        if price > zg:
            return "above"
        if price < zd:
            return "below"
        return "in"

    # --- 一致性检查 ----------------------------------------------------
    def validate(self) -> List[str]:
        errors: List[str] = []

        all_nodes = {
            **self.rsg.pens,
            **self.rsg.segments,
            **self.rsg.trends,
        }

        # 子节点的父节点必须存在
        for child_id, parent_id in self.parent.items():
            if parent_id not in all_nodes:
                errors.append(f"parent_not_found:{child_id}->{parent_id}")

        # 趋势节点应链接至少一个线段
        for trend_id, trend in self.rsg.trends.items():
            if not trend.segments:
                errors.append(f"trend_empty:{trend_id}")
            for seg_id in trend.segments:
                if seg_id not in self.rsg.segments:
                    errors.append(f"trend_segment_missing:{trend_id}->{seg_id}")

        # 每个线段的笔集合必须存在
        for seg_id, segment in self.rsg.segments.items():
            for pen_id in segment.pens:
                if pen_id not in self.rsg.pens:
                    errors.append(f"segment_pen_missing:{seg_id}->{pen_id}")

        return errors

