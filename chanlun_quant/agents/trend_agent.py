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
                    why="上行趋势主导，包络可微放宽",
                    refs=[],
                    methods=["trend_type"],
                    weight=0.3,
                    extras={"envelope_update": {"child_max_ratio": 0.40}},
                )
            )
        elif downs > ups * 1.5:
            out.append(
                Signal(
                    level=self.level,
                    kind="hold",
                    why="下行趋势主导，包络需收紧",
                    refs=[],
                    methods=["trend_type"],
                    weight=0.3,
                    extras={"envelope_update": {"child_max_ratio": 0.25}},
                )
            )
        return out

