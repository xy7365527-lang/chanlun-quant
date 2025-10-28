from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..features.segment_index import SegmentIndex
from .signal import Level, Signal


@dataclass
class SegmentAgent:
    level: Level

    def evaluate(self, seg_idx: SegmentIndex) -> List[Signal]:
        out: List[Signal] = []
        segments = [seg for seg in seg_idx.rsg.segments.values() if seg.level == self.level]
        if len(segments) < 2:
            return out
        current = segments[-1]
        previous = segments[-2]

        if current.divergence == "trend_div":
            out.append(
                Signal(
                    level=self.level,
                    kind="sell",
                    why="段面积背驰兑现",
                    refs=[current.id, previous.id],
                    methods=["divergence", "macd_area", "feature_seq"],
                    weight=0.9,
                )
            )

        if current.trend_state == "up" and current.zhongshu:
            out.append(
                Signal(
                    level=self.level,
                    kind="buy",
                    why="趋势段扩张回踩中枢上沿轻加",
                    refs=[current.id],
                    methods=["trend_type", "zhongshu", "macd_area"],
                    weight=0.4,
                )
            )

        return out

