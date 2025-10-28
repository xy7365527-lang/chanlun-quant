from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from ..features.segment_index import SegmentIndex
from ..rsg.schema import TrendNode


@dataclass
class Envelope:
    net_direction: str
    child_max_ratio: float
    forbid_zone: Optional[Dict[str, float]] = None


def envelope_from_trend(seg_idx: SegmentIndex, position_state, cfg) -> Envelope:
    """基于最高级结构给净方向与容量（MVP: 若最高级 trend_type=range → flat，否则跟随统计方向）。"""
    net = "flat"
    rsg = seg_idx.rsg

    highest_level = None
    if rsg.levels:
        highest_level = rsg.levels[-1]

    trend: Optional[TrendNode] = None
    if highest_level:
        trend_id = f"trend_{highest_level}_0"
        trend = rsg.trends.get(trend_id)

    if trend and trend.trend_type in ("uptrend", "downtrend"):
        net = "long" if trend.trend_type == "uptrend" else "short"
    else:
        ups = sum(1 for seg in rsg.segments.values() if seg.trend_state == "up")
        downs = sum(1 for seg in rsg.segments.values() if seg.trend_state == "down")
        if ups > downs * 1.2:
            net = "long"
        elif downs > ups * 1.2:
            net = "short"

    child_ratio = getattr(cfg, "child_max_ratio", 0.35)
    forbid_zone = getattr(cfg, "forbid_zone", None)
    return Envelope(net_direction=net, child_max_ratio=child_ratio, forbid_zone=forbid_zone)

