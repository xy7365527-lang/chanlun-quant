from __future__ import annotations

from typing import Callable, List, Sequence

from ..config import NestingCfg
from ..features.bridge_stats import nesting_success_ratio
from ..features.segment_index import SegmentIndex
from ..rsg.schema import Level, RSG

DEFAULT_ORDER: List[Level] = ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]


def _order_idx(level: Level) -> int:
    return DEFAULT_ORDER.index(level)


def _normalized_levels(levels: Sequence[Level]) -> List[Level]:
    return sorted(set(levels), key=_order_idx)


def select_levels(
    symbol: str,
    datafeed: Callable[[str, Level], float],
    candidates: Sequence[Level],
    max_levels: int = 4,
) -> List[Level]:
    """Select base levels prioritising M15 and daily bridge levels."""

    if not candidates:
        raise ValueError("缺少候选级别。")

    ordered = _normalized_levels(candidates)
    base = "M15" if "M15" in ordered else ordered[0]
    selection: List[Level] = [base]

    for level in ("H1", "H4", "D1", "W1"):
        if level in ordered and _order_idx(level) > _order_idx(base):
            selection.append(level)
            if len(selection) >= max_levels:
                break
            if level == "D1":
                break

    return selection


def post_validate_levels(
    rsg: RSG,
    seg_idx: SegmentIndex,
    levels: Sequence[Level],
    candidates: Sequence[Level] | None = None,
    nest_cfg: NestingCfg | None = None,
    min_success: float = 0.35,
) -> List[Level]:
    """Insert a bridge level when cross-level resonance success is too low."""

    if not levels:
        rsg.build_info["level_selector_reason"] = "no_levels"
        return []

    normalized = _normalized_levels(levels)
    candidate_seq = candidates or DEFAULT_ORDER
    ordered_candidates = [lv for lv in DEFAULT_ORDER if lv in candidate_seq]
    cfg = nest_cfg or NestingCfg()
    reasons: List[str] = []
    adjusted = list(normalized)

    for idx in range(len(adjusted) - 1):
        low = adjusted[idx]
        high = adjusted[idx + 1]
        try:
            success = nesting_success_ratio(
                seg_idx,
                low,
                high,
                time_win=cfg.time_win,
                price_win=cfg.price_win,
            )
        except Exception:
            success = 1.0
        if success >= min_success:
            continue
        try:
            low_idx = ordered_candidates.index(low)
            high_idx = ordered_candidates.index(high)
        except ValueError:
            continue
        if high_idx - low_idx < 2:
            continue
        bridge = ordered_candidates[low_idx + 1]
        if bridge in adjusted:
            continue
        adjusted = adjusted[: idx + 1] + [bridge] + adjusted[idx + 1 :]
        reasons.append(f"bridge({low}->{bridge}->{high}) succ={success:.2f}")
        break

    if not reasons:
        reasons.append("ok")

    rsg.build_info["level_selector_reason"] = "; ".join(reasons)
    return adjusted
