# file: chanlun_quant/features/bridge_stats.py
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
    """Estimate cross-level resonance success ratio using recent segments."""

    segs = seg_idx.rsg.segments
    highs = [seg for seg in segs.values() if seg.level == high_level]
    lows = [seg for seg in segs.values() if seg.level == low_level]
    if not highs or not lows:
        return 1.0

    highs = highs[-sample_high:]
    lows = lows[-sample_low:]
    low_ids = [seg.id for seg in lows]

    success = 0
    total = 0
    for high_seg in highs:
        total += 1
        if cross_level_nesting(seg_idx, high_seg.id, low_ids, time_win=time_win, price_win=price_win):
            success += 1

    return success / max(1, total)
