from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..core.envelope import Envelope
from ..features.mmd_nesting import cross_level_nesting, tag_mmd_for_segment
from ..features.segment_index import SegmentIndex

VALID_BUCKETS = {"pen", "segment"}
VALID_ACTIONS = {"BUY", "SELL", "HOLD"}


@dataclass
class Proposal:
    bucket: str  # "pen"|"segment"
    action: str  # "BUY"|"SELL"|"HOLD"
    size_delta: float
    node_id: Optional[str] = None
    price_band: Optional[List[float]] = None
    why: str = ""
    refs: Optional[List[str]] = None
    methods: Optional[List[str]] = None


@dataclass
class Plan:
    proposals: List[Proposal]
    envelope_update: Optional[Dict[str, Any]] = None


def _extract_threshold(ctx: Dict[str, Any], keys: Sequence[str], default: float = 0.0) -> float:
    for key in keys:
        value = ctx.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return float(default)


def _has_seg_divergence(seg_idx: SegmentIndex, refs: Sequence[str]) -> bool:
    for ref in refs:
        segment = seg_idx.rsg.segments.get(ref)
        if segment and segment.divergence and segment.divergence != "none":
            return True
    return False


def _near_zhongshu(
    seg_idx: SegmentIndex,
    refs: Sequence[str],
    price_band: Optional[Sequence[float]],
    tol: float = 0.15,
) -> bool:
    if not price_band:
        return True
    lo, hi = min(price_band), max(price_band)
    for ref in refs:
        segment = seg_idx.rsg.segments.get(ref)
        if not segment or not segment.zhongshu:
            continue
        zg = segment.zhongshu.get("zg")
        zd = segment.zhongshu.get("zd")
        if zg is None or zd is None:
            continue
        width = abs(zg - zd)
        lower = zd - tol * width
        upper = zg + tol * width
        return lower <= lo <= upper and lower <= hi <= upper
    return True


def _feature_seq_ok(seg_idx: SegmentIndex, refs: Sequence[str]) -> bool:
    for ref in refs:
        segment = seg_idx.rsg.segments.get(ref)
        if segment and segment.feature_seq and len(segment.feature_seq) >= 3:
            return True
    return False


def _structural_consistent(proposal: Proposal, seg_idx: SegmentIndex) -> bool:
    node_id = proposal.node_id
    if not node_id and proposal.refs:
        node_id = proposal.refs[0]
        proposal.node_id = node_id

    if proposal.bucket == "segment":
        if node_id is None:
            return False
        if node_id in seg_idx.rsg.segments:
            segment = seg_idx.rsg.segments[node_id]
        elif node_id in seg_idx.rsg.pens:
            segment = None
        else:
            return False
    elif proposal.bucket == "pen":
        if node_id is None:
            return False
        if node_id in seg_idx.rsg.pens:
            segment = None
        elif node_id in seg_idx.rsg.segments:
            segment = seg_idx.rsg.segments[node_id]
        else:
            return False
    else:
        return False

    checks = proposal.methods or []
    if "divergence" in checks and segment is not None:
        return seg_idx.seg_area_divergence(segment.level, segment.id)

    if "mmd" in checks and node_id in seg_idx.rsg.pens:
        kinds = ["buy", "sell", "mmd"]
        if not seg_idx.mmd_exists(node_id, kinds):
            return False

    return True


def _allowed_by_envelope(action: str, envelope: Envelope) -> bool:
    if envelope.net_direction == "flat":
        return action == "HOLD"
    if envelope.net_direction == "long":
        return action in ("BUY", "HOLD")
    if envelope.net_direction == "short":
        return action in ("SELL", "HOLD")
    return False


def _within_forbid_zone(price_band: Optional[Sequence[float]], forbid_zone: Optional[Dict[str, Any]]) -> bool:
    if not price_band or not forbid_zone:
        return True
    band_low = min(price_band)
    band_high = max(price_band)
    zone_low = forbid_zone.get("low") or forbid_zone.get("min")
    zone_high = forbid_zone.get("high") or forbid_zone.get("max")

    if zone_low is not None and zone_high is not None:
        return band_high < zone_low or band_low > zone_high
    if zone_low is not None:
        return band_high < zone_low
    if zone_high is not None:
        return band_low > zone_high
    return True


def sanitize_and_clip(
    plan: Plan,
    envelope: Envelope,
    seg_idx: SegmentIndex,
    risk_ctx: Dict[str, Any],
) -> Plan:
    sanitized: List[Proposal] = []
    if not plan.proposals:
        return Plan(proposals=sanitized, envelope_update=plan.envelope_update)

    base_qty = _extract_threshold(risk_ctx, ("core_position_qty", "core_qty", "base_qty"), 0.0)
    max_child_qty = risk_ctx.get("max_child_qty")
    bucket_capacity: Dict[str, float] = {
        key: float(value)
        for key, value in (risk_ctx.get("bucket_capacity") or {}).items()
        if isinstance(value, (int, float))
    }
    pend_eod_hook = risk_ctx.get("pen_eod_hook")
    guard_strict = bool(risk_ctx.get("guard_strict", False))
    core_qty = float(risk_ctx.get("core_qty", 0.0))

    min_step = _extract_threshold(risk_ctx, ("min_step", "min_qty"), 0.0)
    fee_threshold = _extract_threshold(risk_ctx, ("fee_threshold", "fee_cost"), 0.0)
    size_threshold = max(min_step, fee_threshold, 0.0)

    segments = seg_idx.rsg.segments
    pens = seg_idx.rsg.pens

    total_size = 0.0

    for proposal in plan.proposals:
        if proposal.bucket not in VALID_BUCKETS or proposal.action not in VALID_ACTIONS:
            continue
        try:
            raw_size = float(proposal.size_delta)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(raw_size):
            continue

        size_abs = abs(raw_size)
        refs = list(proposal.refs or [])
        methods = list(proposal.methods or [])

        why_notes: List[str] = [proposal.why] if proposal.why else []

        bad_refs = [
            ref for ref in refs if ref not in segments and ref not in pens
        ]
        if bad_refs:
            why_notes.append(" ".join(f"[bad_ref:{ref}]" for ref in bad_refs))
            if guard_strict:
                continue

        seg_refs = [ref for ref in refs if ref in segments]
        pen_refs = [ref for ref in refs if ref in pens]

        if proposal.bucket == "segment" and not seg_refs and pen_refs:
            why_notes.append("[refs_mismatch_pen_for_segment]")
            if guard_strict:
                continue
        if proposal.bucket == "pen" and not pen_refs and seg_refs:
            why_notes.append("[refs_mismatch_segment_for_pen]")
            if guard_strict:
                continue

        if "divergence" in methods and refs and not _has_seg_divergence(seg_idx, refs):
            why_notes.append("[no_divergence_evidence]")
            if guard_strict:
                continue
        if "zhongshu" in methods and not _near_zhongshu(seg_idx, refs, proposal.price_band):
            why_notes.append("[price_band_out_of_zhongshu]")
            if guard_strict:
                continue
        if proposal.bucket == "segment" and "feature_seq" in methods and refs and not _feature_seq_ok(seg_idx, refs):
            why_notes.append("[feature_seq_unstable]")
            if guard_strict:
                continue
        if proposal.bucket == "segment" and refs:
            unstable = False
            for ref in refs:
                seg = seg_idx.rsg.segments.get(ref)
                if seg and "feature_unstable" in getattr(seg, "tags", []):
                    unstable = True
                    break
            if unstable:
                why_notes.append("[feature_unstable_forbid]")
                if guard_strict:
                    continue
        if "mmd" in methods and refs:
            any_mmd = False
            strict_mmd = False
            for ref in refs:
                seg = seg_idx.rsg.segments.get(ref)
                if not seg:
                    continue
                if seg.mmds:
                    any_mmd = True
                    if any(tag and tag[0] in "123" for tag in seg.mmds):
                        strict_mmd = True
                        break
                else:
                    tags = tag_mmd_for_segment(seg_idx, ref)
                    if tags:
                        seg.mmds.extend(tags)
                        any_mmd = True
                        if any(tag and tag[0] in "123" for tag in tags):
                            strict_mmd = True
                            break
            if not any_mmd:
                why_notes.append("[no_mmd_evidence]")
                if guard_strict:
                    continue
            if not strict_mmd:
                why_notes.append("[no_strict_mmd]")
                if guard_strict:
                    continue
            action_side = (
                "buy"
                if proposal.action == "BUY"
                else ("sell" if proposal.action == "SELL" else "hold")
            )
            if action_side in {"buy", "sell"}:
                side_ok = False
                for ref in refs:
                    seg = seg_idx.rsg.segments.get(ref)
                    if not seg:
                        continue
                    tags = seg.mmds or []
                    if action_side == "buy" and any(tag.endswith("buy") for tag in tags):
                        side_ok = True
                        break
                    if action_side == "sell" and any(tag.endswith("sell") for tag in tags):
                        side_ok = True
                        break
                if not side_ok:
                    why_notes.append("[mmd_direction_mismatch]")
                    if guard_strict:
                        continue
        if "nesting" in methods and refs and len(refs) >= 2:
            high_ref = refs[0]
            low_refs = refs[1:]
            if not cross_level_nesting(seg_idx, high_ref, low_refs):
                why_notes.append("[no_nesting_window]")
                if guard_strict:
                    continue
        if proposal.price_band and "zhongshu" in methods:
            lo_band, hi_band = min(proposal.price_band), max(proposal.price_band)
            span = hi_band - lo_band
            zhongshu_span = None
            for ref in refs:
                seg = seg_idx.rsg.segments.get(ref)
                if seg and seg.zhongshu:
                    zhongshu_span = seg.zhongshu.get("span")
                    if zhongshu_span:
                        break
            min_step_abs = float(risk_ctx.get("min_step_abs", 0.0))
            k_grid = float(risk_ctx.get("k_grid", 0.25))
            if zhongshu_span is not None:
                min_step_abs = max(min_step_abs, zhongshu_span * k_grid)
            if span < max(min_step_abs, 1e-9):
                why_notes.append(f"[step_too_small<{min_step_abs:.4f}]")
                if guard_strict:
                    continue

        if proposal.action == "HOLD" or size_abs <= 0 or size_abs < size_threshold:
            sanitized.append(
                Proposal(
                    bucket=proposal.bucket,
                    action="HOLD",
                    size_delta=0.0,
                    node_id=proposal.node_id,
                    price_band=proposal.price_band,
                    why=" ".join(why_notes).strip(),
                    refs=refs or None,
                    methods=methods or None,
                )
            )
            continue

        if not _structural_consistent(proposal, seg_idx):
            continue

        if not _allowed_by_envelope(proposal.action, envelope):
            continue

        if not _within_forbid_zone(proposal.price_band, envelope.forbid_zone):
            continue

        allowed_capacity = None
        if proposal.bucket in bucket_capacity:
            allowed_capacity = bucket_capacity[proposal.bucket]
        elif max_child_qty is not None:
            allowed_capacity = float(max_child_qty)
        elif base_qty:
            allowed_capacity = abs(base_qty) * envelope.child_max_ratio

        if allowed_capacity is not None:
            size_abs = min(size_abs, max(0.0, allowed_capacity))

        total_size += size_abs

        sanitized.append(
            Proposal(
                bucket=proposal.bucket,
                action=proposal.action,
                size_delta=size_abs,
                node_id=proposal.node_id,
                price_band=proposal.price_band,
                why=" ".join(filter(None, why_notes)).strip(),
                refs=refs or None,
                methods=methods or None,
            )
        )

    if pend_eod_hook:
        pass

    if core_qty > 0:
        max_cap = envelope.child_max_ratio * core_qty
        if total_size > max_cap > 0:
            scale = max_cap / total_size
            for proposal in sanitized:
                proposal.size_delta *= scale

    return Plan(proposals=sanitized, envelope_update=plan.envelope_update)


def fuse_to_net_orders(plan: Plan, plan_id: Optional[str] = None) -> List[Dict[str, Any]]:
    aggregates: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for proposal in plan.proposals:
        if proposal.action == "HOLD":
            continue
        qty = float(proposal.size_delta)
        if qty <= 0:
            continue
        side = "buy" if proposal.action == "BUY" else "sell"
        key = (proposal.bucket, side)
        entry = aggregates.setdefault(
            key,
            {
                "bucket": proposal.bucket,
                "side": side,
                "qty": 0.0,
                "price_low": None,
                "price_high": None,
                "reasons": [],
                "refs": [],
                "methods": [],
            },
        )
        entry["qty"] += qty
        if proposal.price_band:
            low = min(proposal.price_band)
            high = max(proposal.price_band)
            entry["price_low"] = low if entry["price_low"] is None else min(entry["price_low"], low)
            entry["price_high"] = high if entry["price_high"] is None else max(entry["price_high"], high)
        if proposal.why:
            entry["reasons"].append(proposal.why)
        if proposal.refs:
            entry["refs"].extend(proposal.refs)
        if proposal.methods:
            entry["methods"].extend(proposal.methods)

    orders: List[Dict[str, Any]] = []
    for entry in aggregates.values():
        order: Dict[str, Any] = {
            "bucket": entry["bucket"],
            "side": entry["side"],
            "qty": entry["qty"],
        }
        if entry["price_low"] is not None and entry["price_high"] is not None:
            order["price_band"] = [entry["price_low"], entry["price_high"]]
        if entry["reasons"]:
            order["why"] = "; ".join(dict.fromkeys(entry["reasons"]))
        if entry["refs"]:
            order["refs"] = list(dict.fromkeys(entry["refs"]))
        if entry["methods"]:
            order["methods"] = list(dict.fromkeys(entry["methods"]))
        if plan_id is not None:
            order["idempotency_key"] = plan_id
        orders.append(order)

    return orders
