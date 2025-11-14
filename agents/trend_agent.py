from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..features.segment_index import SegmentIndex
from .signal import Level, Signal


@dataclass
class TrendAgent:
    level: Level

    def evaluate(self, seg_idx: SegmentIndex) -> List[Signal]:
        out: List[Signal] = []
        segments = [seg for seg in seg_idx.rsg.segments.values() if seg.level == self.level]
        ups = sum(1 for seg in segments if seg.trend_state == "up")
        downs = sum(1 for seg in segments if seg.trend_state == "down")

        if ups > downs * 1.5:
            out.append(
                Signal(
                    level=self.level,
                    kind="hold",
                    why="趋势上行占优，放宽子仓比例提示",
                    refs=[],
                    methods=["trend_type"],
                    weight=0.3,
                    confidence=0.55,
                    strength=0.45,
                    tags=["trend_up"],
                    extras={"envelope_update": {"child_max_ratio": 0.40}, "ups": ups, "downs": downs},
                )
            )
        elif downs > ups * 1.5:
            out.append(
                Signal(
                    level=self.level,
                    kind="hold",
                    why="趋势下行占优，收紧子仓比例提示",
                    refs=[],
                    methods=["trend_type"],
                    weight=0.3,
                    confidence=0.55,
                    strength=0.45,
                    tags=["trend_down"],
                    extras={"envelope_update": {"child_max_ratio": 0.25}, "ups": ups, "downs": downs},
                )
            )
        return out
