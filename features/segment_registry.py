from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

from .segment_index import SegmentIndex


@dataclass
class ConsistencyReport:
    ok: bool
    issues: List[str]


def add_pen(seg_idx: SegmentIndex, pen: Any) -> None:
    """Register a pen into the RSG cache and leave linkage to subsequent updates."""

    seg_idx.rsg.pens[pen.id] = pen


def add_segment(seg_idx: SegmentIndex, seg: Any, parent_id: str | None = None) -> None:
    """Register a segment and update optional parent edge."""

    seg_idx.rsg.segments[seg.id] = seg
    if parent_id and parent_id in seg_idx.rsg.segments:
        seg_idx.rsg.edges.append({"parent": parent_id, "child": seg.id, "rel": "contains"})


def link_edge(seg_idx: SegmentIndex, parent_id: str, child_id: str) -> None:
    seg_idx.rsg.edges.append({"parent": parent_id, "child": child_id, "rel": "contains"})


def is_consistent(seg_idx: SegmentIndex) -> ConsistencyReport:
    issues: List[str] = []
    seen_segments: set[str] = set()

    for seg_id, segment in seg_idx.rsg.segments.items():
        if seg_id in seen_segments:
            issues.append(f"dup_segment_id:{seg_id}")
        seen_segments.add(seg_id)
        if segment.i1 < segment.i0:
            issues.append(f"bad_span:{seg_id}")
        feature_seq = getattr(segment, "feature_seq", None)
        if feature_seq is not None and len(feature_seq) == 0:
            issues.append(f"empty_feature:{seg_id}")

    for edge in seg_idx.rsg.edges:
        parent = seg_idx.rsg.segments.get(edge.get("parent"))
        child = seg_idx.rsg.segments.get(edge.get("child"))
        if parent and child:
            if not (child.i0 >= parent.i0 and child.i1 <= parent.i1):
                issues.append(f"parent_window_violation:{parent.id}->{child.id}")

    return ConsistencyReport(ok=not issues, issues=issues)
