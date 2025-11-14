from __future__ import annotations

from .segment_index import SegmentIndex
from .mmd_nesting import cross_level_nesting


def nesting_success_ratio(
    seg_idx: SegmentIndex,
    low_level: str,
    high_level: str,
    sample_high: int = 12,
    sample_low: int = 24,
    time_win: float = 0.30,
    price_win: float = 0.15,
) -> float:
    segments = seg_idx.rsg.segments
    highs = [seg for seg in segments.values() if seg.level == high_level]
    lows = [seg for seg in segments.values() if seg.level == low_level]
    if not highs or not lows:
        return 1.0
    highs = highs[-sample_high:]
    lows = lows[-sample_low:]
    total = 0
    success = 0
    low_ids = [seg.id for seg in lows]
    for high in highs:
        total += 1
        if cross_level_nesting(seg_idx, high.id, low_ids, time_win, price_win):
            success += 1
    return success / max(1, total)
