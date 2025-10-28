from __future__ import annotations

from typing import List, Sequence

from ..config import NestingCfg
from ..selector.bridge_eval import best_bridge_between
from ..rsg.schema import Level, RSG

DEFAULT_ORDER: List[Level] = ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]


def _order_idx(level: Level) -> int:
    return DEFAULT_ORDER.index(level)


def select_levels(symbol: str, datafeed, candidates: Sequence[Level]) -> List[Level]:
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
    if not levels:
        return []

    candidates_list = list(candidates or DEFAULT_ORDER)
    nest_cfg = nest_cfg or NestingCfg()
    adjusted: List[Level] = list(levels)
    reasons: List[str] = []

    idx = 0
    while idx < len(adjusted) - 1:
        low = adjusted[idx]
        high = adjusted[idx + 1]
        if low not in candidates_list or high not in candidates_list:
            reasons.append(f"skip({low}-{high})")
            idx += 1
            continue
        bridge, detail = best_bridge_between(
            seg_idx,
            low,
            high,
            candidates_list,
            min_success=min_success,
            time_win=nest_cfg.time_win,
            price_win=nest_cfg.price_win,
        )
        if bridge and bridge not in adjusted:
            adjusted = adjusted[: idx + 1] + [bridge] + adjusted[idx + 1 :]
            reasons.append(f"{low}->{bridge}->{high} ({detail})")
            idx += 1  # re-evaluate with new bridge as low->bridge next
        else:
            reasons.append(detail)
        idx += 1

    rsg.build_info["level_selector_reason"] = " | ".join(reasons) if reasons else "ok"
    return adjusted
