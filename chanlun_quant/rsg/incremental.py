from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .build import build_level_pens_segments, _calc_segment_macd, _detect_zhongshu, _divergence_between
from .schema import Level, PenNode, RSG, SegmentNode, TrendNode

DEFAULT_ORDER: List[Level] = ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]

def _order_idx(level: Level) -> int:
    return DEFAULT_ORDER.index(level)


@dataclass
class RSGBuilder:
    symbol: str
    levels: List[Level]
    window: int = 400
    _bars: Dict[Level, Dict[str, List[float]]] = field(default_factory=dict)
    _pens: Dict[Level, List[PenNode]] = field(default_factory=dict)
    _segs: Dict[Level, List[SegmentNode]] = field(default_factory=dict)

    def set_level_bars(self, level: Level, bars: Dict[str, List[float]]) -> None:
        def tail(arr: List[float]) -> List[float]:
            return arr[-self.window :] if len(arr) > self.window else arr

        self._bars[level] = {key: tail(values) for key, values in bars.items()}

    def rebuild_level(self, level: Level) -> None:
        bars = self._bars[level]
        pens, segs = build_level_pens_segments(bars["close"], bars["high"], bars["low"], bars["macd"], level)
        _calc_segment_macd(segs, pens)
        pen_lookup = {pen.id: pen for pen in pens}
        for seg in segs:
            seg_pens = [pen_lookup[pid] for pid in seg.pens if pid in pen_lookup]
            _detect_zhongshu(seg, seg_pens)
        for idx in range(1, len(segs)):
            segs[idx].divergence = _divergence_between(segs[idx - 1], segs[idx], pen_lookup=pen_lookup, r_seg=0.85)
        self._pens[level] = pens
        self._segs[level] = segs

    def ingest(self, level_bars: Dict[Level, Dict[str, List[float]]]) -> RSG:
        ordered_levels = sorted(self.levels, key=_order_idx)
        for level in ordered_levels:
            self.set_level_bars(level, level_bars[level])
            self.rebuild_level(level)

        rsg = RSG(symbol=self.symbol, levels=list(ordered_levels))
        level_seg_ids: Dict[Level, List[str]] = {}
        for level in ordered_levels:
            for pen in self._pens.get(level, []):
                rsg.pens[pen.id] = pen
            for seg in self._segs.get(level, []):
                rsg.segments[seg.id] = seg
            level_seg_ids[level] = [seg.id for seg in self._segs.get(level, [])]

        def _edge(parent_id: str, child_id: str, low: Level, high: Level) -> None:
            rsg.edges.append({"parent": parent_id, "child": child_id, "rel": "contains", "lv": (low, high)})

        for idx in range(len(ordered_levels) - 1):
            low_level = ordered_levels[idx]
            high_level = ordered_levels[idx + 1]
            for sid_low in level_seg_ids.get(low_level, []):
                low_seg = rsg.segments[sid_low]
                for sid_high in level_seg_ids.get(high_level, []):
                    high_seg = rsg.segments[sid_high]
                    if low_seg.i0 >= high_seg.i0 and low_seg.i1 <= high_seg.i1:
                        _edge(high_seg.id, low_seg.id, low_level, high_level)

        for level in ordered_levels:
            trend_id = f"trend_{level}_0"
            rsg.trends[trend_id] = TrendNode(
                id=trend_id,
                level=level,
                segments=level_seg_ids.get(level, []),
                trend_type="range",
                confirmed=False,
            )

        rsg.build_info["incremental"] = True
        rsg.build_info["window"] = self.window
        return rsg
