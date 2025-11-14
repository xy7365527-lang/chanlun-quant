from __future__ import annotations

import math
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
                    why="段级 MACD 面积背驰，优先兑现",
                    refs=[current.id, previous.id],
                    methods=["divergence", "macd_area", "feature_seq", "mmd"],
                    weight=0.95,
                    confidence=0.8,
                    strength=0.8,
                    entry_band=None,
                    take_band=None,
                    t_window=8,
                    tags=current.mmds or ["3sell"],
                )
            )

        if current.trend_state == "up" and current.zhongshu:
            zs = current.zhongshu
            zg = float(zs.get("zg", 0.0))
            zd = float(zs.get("zd", 0.0))
            zm = float(zs.get("zm", (zg + zd) / 2.0))
            span = float(zs.get("span", zg - zd))
            if all(map(math.isfinite, (zg, zd, zm, span))) and span > 0:
                out.append(
                    Signal(
                        level=self.level,
                        kind="buy",
                        why="上行趋势段靠近上沿回踩，可轻量跟进",
                        refs=[current.id],
                        methods=["trend_type", "zhongshu", "macd_area", "mmd"],
                        weight=0.5,
                        confidence=0.55,
                        strength=0.5,
                        entry_band=[zm, zg],
                        stop_band=[max(zd - span * 0.1, zd - span * 0.3), zd],
                        take_band=[zg, zg + span * 0.2],
                        t_window=10,
                        tags=current.mmds or [],
                        extras={"zhongshu": zs},
                    )
                )

        return out
