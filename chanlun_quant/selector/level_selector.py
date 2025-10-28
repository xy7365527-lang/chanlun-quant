from __future__ import annotations

from typing import List, Sequence

from ..config import NestingCfg
from ..features.bridge_stats import nesting_success_ratio
from ..rsg.schema import Level, RSG

DEFAULT_ORDER: List[Level] = ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]


def _order_idx(level: Level) -> int:
    return DEFAULT_ORDER.index(level)


def select_levels(symbol: str, datafeed, candidates: Sequence[Level]) -> List[Level]:
    """Basic level selection prioritising M15 plus higher frames."""
    ordered = [level for level in DEFAULT_ORDER if level in candidates]
    if not ordered:
        raise ValueError("No valid level candidates provided")
    base = "M15" if "M15" in ordered else ordered[0]
    levels = [base]
    for level in ["H1", "H4", "D1", "W1"]:
        if level in ordered and _order_idx(level) > _order_idx(base):
            levels.append(level)
            if level == "D1":
                break
    return levels


def post_validate_levels(
    rsg: RSG,
    seg_idx,
    levels: Sequence[Level],
    candidates: Sequence[Level] | None = None,
    nest_cfg: NestingCfg | None = None,
    min_success: float = 0.35,
) -> List[Level]:
    """Insert bridge levels when adjacent success ratios fall below threshold."""
    if not levels:
        return []

    candidates = list(candidates or DEFAULT_ORDER)
    nest_cfg = nest_cfg or NestingCfg()
    adjusted = list(levels)
    reasons: List[str] = []

    for idx in range(len(adjusted) - 1):
        low = adjusted[idx]
        high = adjusted[idx + 1]
        success = nesting_success_ratio(
            seg_idx,
            low,
            high,
            time_win=nest_cfg.time_win,
            price_win=nest_cfg.price_win,
        )
        if success < min_success:
            low_idx = candidates.index(low)
            high_idx = candidates.index(high)
            if high_idx - low_idx >= 2:
                bridge = candidates[low_idx + 1]
                if bridge not in adjusted:
                    adjusted = adjusted[: idx + 1] + [bridge] + adjusted[idx + 1 :]
                    reasons.append(f"bridge({low}->{bridge}->{high}) succ={success:.2f}")
                    break

    rsg.build_info["level_selector_reason"] = "; ".join(reasons) if reasons else "ok"
    return adjusted
