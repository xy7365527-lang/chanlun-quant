from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..features.segment_index import SegmentIndex
from .signal import Level, Signal


@dataclass
class PenAgent:
    level: Level

    def evaluate(self, seg_idx: SegmentIndex, last_price: float) -> List[Signal]:
        out: List[Signal] = []
        segments = [seg for seg in seg_idx.rsg.segments.values() if seg.level == self.level]
        if not segments:
            return out
        segment = segments[-1]
        if not segment.zhongshu:
            return out
        zg = segment.zhongshu.get("zg")
        zd = segment.zhongshu.get("zd")
        if zg is None or zd is None:
            return out
        mid = (zg + zd) / 2.0
        if not (zd <= last_price <= zg):
            return out

        methods = ["zhongshu", "macd_area"]
        refs = [segment.id]
        if last_price <= mid:
            out.append(
                Signal(
                    level=self.level,
                    kind="buy",
                    why="中枢下半区低吸T+0",
                    refs=refs,
                    methods=methods,
                    weight=0.6,
                )
            )
        if last_price >= mid:
            out.append(
                Signal(
                    level=self.level,
                    kind="sell",
                    why="中枢上半区高抛T+0",
                    refs=refs,
                    methods=methods,
                    weight=0.6,
                )
            )
        return out

