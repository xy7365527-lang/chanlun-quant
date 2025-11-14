from __future__ import annotations

from typing import Dict, List, Sequence

from ..config import NestingCfg, SelectorAdvCfg
from ..features.bridge_stats import nesting_success_ratio
from ..features.market_stats import density_pens_per_100bars, natr, zhongshu_cover_ratio
from ..rsg.schema import Level, RSG

DEFAULT_ORDER: List[Level] = ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]


def _order_idx(level: Level) -> int:
    return DEFAULT_ORDER.index(level)


def select_levels(symbol: str, datafeed, candidates: Sequence[Level]) -> List[Level]:
    ordered = [level for level in DEFAULT_ORDER if level in candidates]
    if not ordered:
        raise ValueError("No valid level candidates provided")
    base = "M15" if "M15" in ordered else ordered[0]
    picked = [base]
    for up in ["H1", "H4", "D1", "W1"]:
        if up in ordered and _order_idx(up) > _order_idx(base):
            picked.append(up)
            if up == "D1":
                break
    return picked


def post_validate_levels(
    rsg: RSG,
    seg_idx,
    levels: Sequence[Level],
    candidates: Sequence[Level] | None = None,
    adv: SelectorAdvCfg | None = None,
    nest_cfg: NestingCfg | None = None,
    bars_by_level: Dict[Level, Dict[str, List[float]]] | None = None,
) -> List[Level]:
    if not levels:
        return []

    candidates_list = list(candidates or DEFAULT_ORDER)
    adv = adv or SelectorAdvCfg()
    nest_cfg = nest_cfg or NestingCfg()
    adjusted: List[Level] = list(levels)
    reasons: List[str] = []

    # Step 1: baseline level diagnostics
    if bars_by_level:
        base_level = adjusted[0]
        bars = bars_by_level.get(base_level, {})
        highs = bars.get("high", [])
        lows = bars.get("low", [])
        closes = bars.get("close", [])
        nat = natr(highs, lows, closes, n=14)
        density = density_pens_per_100bars(rsg, base_level, len(closes))
        cover = zhongshu_cover_ratio(rsg, base_level, highs, lows)
        # Promote the base level when structural information looks too sparse or quiet.
        if nat < adv.natr_low or density < adv.density_low or cover < adv.zs_cover_min:
            idx = candidates_list.index(base_level)
            if idx + 1 < len(candidates_list):
                new_base = candidates_list[idx + 1]
                adjusted = [new_base] + [lv for lv in adjusted if _order_idx(lv) > _order_idx(new_base)]
                reasons.append(
                    f"promote_base:{base_level}->{new_base} "
                    f"(natr={nat:.4f},density={density:.2f},cover={cover:.3f})"
                )

    # Step 2: bridge missing intermediate levels when nesting success is low
    idx = 0
    while idx < len(adjusted) - 1:
        low = adjusted[idx]
        high = adjusted[idx + 1]
        if low not in candidates_list or high not in candidates_list:
            reasons.append(f"skip({low}-{high})")
            idx += 1
            continue
        success = nesting_success_ratio(
            seg_idx,
            low,
            high,
            time_win=nest_cfg.time_win,
            price_win=nest_cfg.price_win,
        )
        if success < adv.nesting_min_success:
            low_idx = candidates_list.index(low)
            high_idx = candidates_list.index(high)
            if high_idx - low_idx >= 2:
                bridge = candidates_list[low_idx + 1]
                if bridge not in adjusted:
                    adjusted = adjusted[: idx + 1] + [bridge] + adjusted[idx + 1 :]
                    reasons.append(f"bridge:{low}->{bridge}->{high} succ={success:.2f}")
                    idx += 1
                    continue
        idx += 1

    rsg.build_info["level_selector_reason"] = " | ".join(reasons) if reasons else "ok"
    return adjusted
