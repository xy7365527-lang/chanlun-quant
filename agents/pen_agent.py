from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, List, Optional

from ..features.segment_index import SegmentIndex
from .signal import Level, Signal


@dataclass
class PenAgent:
    level: Level

    def _latest_segment(self, seg_idx: SegmentIndex) -> Optional[Any]:
        segments = [seg for seg in seg_idx.rsg.segments.values() if seg.level == self.level]
        return segments[-1] if segments else None

    def evaluate(self, seg_idx: SegmentIndex, last_price: float) -> List[Signal]:
        out: List[Signal] = []
        segment = self._latest_segment(seg_idx)
        if segment is None or not segment.zhongshu:
            return out

        zhongshu = segment.zhongshu
        zg = float(zhongshu.get("zg", 0.0))
        zd = float(zhongshu.get("zd", 0.0))
        zm = float(zhongshu.get("zm", (zg + zd) / 2.0))
        span = float(zhongshu.get("span", zg - zd))
        if not all(map(math.isfinite, (zg, zd, zm, span))) or span <= 0.0:
            return out

        lower_band = [zd, min(zg, zd + span * 0.25)]
        upper_band = [max(zd, zg - span * 0.25), zg]
        refs = [segment.id]
        methods = ["zhongshu", "macd_area"]
        extras = {"zhongshu": zhongshu}

        if last_price <= zm:
            out.append(
                Signal(
                    level=self.level,
                    kind="buy",
                    why="中枢下半区 T+0 低吸",
                    refs=refs,
                    methods=methods,
                    weight=0.7,
                    confidence=0.65,
                    strength=0.55,
                    entry_band=lower_band,
                    take_band=[zm, zg],
                    stop_band=[max(zd - span * 0.1, zd - span * 0.3), zd],
                    t_window=6,
                    tags=["T0_buy"],
                    extras=extras,
                )
            )
        if last_price >= zm:
            out.append(
                Signal(
                    level=self.level,
                    kind="sell",
                    why="中枢上半区 T+0 高抛",
                    refs=refs,
                    methods=methods,
                    weight=0.7,
                    confidence=0.65,
                    strength=0.55,
                    entry_band=upper_band,
                    take_band=[zd, zm],
                    stop_band=[zg, min(zg + span * 0.3, zg + span * 0.5)],
                    t_window=6,
                    tags=["T0_sell"],
                    extras=extras,
                )
            )
        return out
