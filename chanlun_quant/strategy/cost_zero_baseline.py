from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from ..features.segment_index import SegmentIndex
from ..fugue.level_coordinator import Plan, Proposal
from ..rsg.schema import SegmentNode


@dataclass
class BaselineConfig:
    r_pen: float = 0.80
    r_seg: float = 0.85
    grid_k: float = 0.25
    segment_sell_qty: float = 100.0
    pen_grid_qty: float = 50.0


class CostZeroBaseline:
    """纯规则回退：段级背驰兑现 + 笔级中枢内 T+0。"""

    def __init__(self, cfg: Optional[BaselineConfig] = None) -> None:
        self.cfg = cfg or BaselineConfig()

    def _find_recent_divergence_segment(self, seg_idx: SegmentIndex) -> Optional[SegmentNode]:
        segments = list(seg_idx.rsg.segments.values())
        segments.sort(key=lambda seg: seg.i1, reverse=True)
        for segment in segments:
            if segment.divergence == "trend_div":
                return segment
        return None

    def _find_central_segment(self, seg_idx: SegmentIndex, price: float) -> Optional[SegmentNode]:
        segments = list(seg_idx.rsg.segments.values())
        segments.sort(key=lambda seg: seg.i1, reverse=True)
        for segment in segments:
            if not segment.zhongshu:
                continue
            zg = segment.zhongshu.get("zg")
            zd = segment.zhongshu.get("zd")
            if zg is None or zd is None:
                continue
            if zd <= price <= zg:
                return segment
        return None

    def propose(self, seg_idx: SegmentIndex, last_price: float) -> Plan:
        proposals: List[Proposal] = []

        divergence_segment = self._find_recent_divergence_segment(seg_idx)
        if divergence_segment:
            proposals.append(
                Proposal(
                    bucket="segment",
                    action="SELL",
                    size_delta=self.cfg.segment_sell_qty,
                    node_id=divergence_segment.id,
                    why="段面积背驰兑现",
                )
            )

        central_segment = self._find_central_segment(seg_idx, last_price)
        if central_segment:
            buy_qty = self.cfg.pen_grid_qty
            sell_qty = self.cfg.pen_grid_qty
            proposals.append(
                Proposal(
                    bucket="pen",
                    action="BUY",
                    size_delta=buy_qty,
                    node_id=central_segment.pens[-1] if central_segment.pens else None,
                    why="中枢内低吸T+0",
                )
            )
            proposals.append(
                Proposal(
                    bucket="pen",
                    action="SELL",
                    size_delta=sell_qty,
                    node_id=central_segment.pens[-1] if central_segment.pens else None,
                    why="中枢内高抛T+0",
                )
            )

        return Plan(proposals=proposals, envelope_update=None)

