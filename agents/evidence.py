from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

from ..features.mmd_nesting import cross_level_nesting
from ..features.segment_index import SegmentIndex
from .signal import Signal


@dataclass
class EvidenceWeights:
    mmd_1: float = 0.08
    mmd_2: float = 0.12
    mmd_3: float = 0.18
    mmd_3weak: float = 0.05
    macd_rel: float = 0.25
    eff_price: float = 0.10
    zs_distance: float = 0.12
    stable_bonus: float = 0.08
    unstable_penalty: float = -0.15
    nesting_endorse: float = 0.10


def _mmd_tier(tags: List[str] | None) -> Tuple[float, str]:
    if not tags:
        return 0.0, ""
    if any(tag.startswith("3weak") for tag in tags):
        return 0.05, "3weak"
    if any(tag.startswith("3") for tag in tags):
        return 0.18, "3"
    if any(tag.startswith("2") for tag in tags):
        return 0.12, "2"
    if any(tag.startswith("1") for tag in tags):
        return 0.08, "1"
    return 0.0, ""


def _seg_rel_strength(seg_idx: SegmentIndex, seg_id: str, lookback: int = 14) -> float:
    segment = seg_idx.rsg.segments.get(seg_id)
    if segment is None:
        return 0.5
    peers = [seg for seg in seg_idx.rsg.segments.values() if seg.level == segment.level]
    if not peers:
        return 0.5
    tail = peers[-lookback:] if len(peers) >= lookback else peers
    baseline = sum(abs(seg.macd_area_abs) for seg in tail) / len(tail) if tail else 1e-9
    rel = abs(segment.macd_area_abs) / max(baseline, 1e-9)
    return max(0.0, min(rel / 2.0, 1.0))


def _zs_distance(seg_idx: SegmentIndex, seg_id: str) -> float:
    segment = seg_idx.rsg.segments.get(seg_id)
    if segment is None or not segment.zhongshu:
        return 0.5
    zg = float(segment.zhongshu.get("zg", 0.0))
    zd = float(segment.zhongshu.get("zd", 0.0))
    span = max(1e-9, zg - zd)
    hi_edge = abs(zg - zd) / span
    mid = float(segment.zhongshu.get("zm", (zg + zd) / 2.0))
    dist_edge = max(abs(zg - mid), abs(mid - zd)) / span
    return max(0.0, min(max(hi_edge, dist_edge), 1.0))


def _nesting_endorse(seg_idx: SegmentIndex, seg_id: str) -> float:
    parent_ids = [edge["parent"] for edge in seg_idx.rsg.edges if edge.get("child") == seg_id]
    if not parent_ids:
        return 0.0
    parent = parent_ids[0]
    ok = cross_level_nesting(seg_idx, parent, [seg_id], time_win=0.25, price_win=0.10)
    return 0.10 if ok else 0.0


def _efficiency_score(segment) -> float:
    eff = float(getattr(segment, "macd_eff_price", 0.0))
    if not math.isfinite(eff) or eff <= 0:
        return 0.5
    norm = eff / (eff + 1.0)
    return max(0.0, min(norm, 1.0))


def score_with_evidence(signal: Signal, seg_idx: SegmentIndex, weights: EvidenceWeights = EvidenceWeights()) -> Signal:
    confidence = signal.confidence or 0.5
    strength = signal.strength or 0.5

    seg_refs = [ref for ref in (signal.refs or []) if ref.startswith("seg_")]
    if seg_refs:
        seg_id = seg_refs[0]
        segment = seg_idx.rsg.segments.get(seg_id)

        tier, tier_name = _mmd_tier(getattr(segment, "mmds", None) if segment else None)
        confidence += tier

        strength = max(strength, _seg_rel_strength(seg_idx, seg_id))
        if segment is not None:
            strength = max(strength, _efficiency_score(segment))

        strength = max(strength, _zs_distance(seg_idx, seg_id))

        tags = getattr(segment, "tags", None) if segment else None
        if tags and "feature_unstable" in tags:
            confidence += weights.unstable_penalty
            strength = max(0.0, strength + weights.unstable_penalty)
        else:
            confidence += weights.stable_bonus

        confidence += _nesting_endorse(seg_idx, seg_id)

    confidence = max(0.0, min(confidence, 1.0))
    strength = max(0.0, min(strength, 1.0))

    return Signal(
        level=signal.level,
        kind=signal.kind,
        why=signal.why,
        refs=signal.refs,
        methods=signal.methods,
        weight=signal.weight,
        confidence=confidence,
        strength=strength,
        entry_band=signal.entry_band,
        stop_band=signal.stop_band,
        take_band=signal.take_band,
        t_window=signal.t_window,
        tags=signal.tags,
        extras=signal.extras,
    )
