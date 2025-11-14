from __future__ import annotations

from typing import List, Optional, Tuple

from ..features.bridge_stats import nesting_success_ratio


def best_bridge_between(
    seg_idx,
    low: str,
    high: str,
    candidates: List[str],
    min_success: float = 0.35,
    time_win: float = 0.30,
    price_win: float = 0.15,
) -> Tuple[Optional[str], str]:
    base_succ = nesting_success_ratio(seg_idx, low, high, time_win=time_win, price_win=price_win)
    if base_succ >= min_success:
        return None, f"ok({low}-{high}) succ={base_succ:.2f}"

    idx_low = candidates.index(low)
    idx_high = candidates.index(high)
    best = None
    best_score = -1.0
    reason = f"base_succ={base_succ:.2f}; "

    for idx in range(idx_low + 1, idx_high):
        bridge = candidates[idx]
        succ_low = nesting_success_ratio(
            seg_idx,
            low,
            bridge,
            time_win=time_win,
            price_win=price_win,
        )
        succ_high = nesting_success_ratio(
            seg_idx,
            bridge,
            high,
            time_win=time_win,
            price_win=price_win,
        )
        score = (succ_low * succ_high) ** 0.5
        if score > best_score:
            best_score = score
            best = bridge

    if best is None:
        return None, reason + "no_candidate"
    return best, reason + f"bridge={best}, score={best_score:.2f}"
