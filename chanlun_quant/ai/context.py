from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence

from chanlun_quant.types import (
    MultiLevelMapping,
    PositionState,
    Signal,
    StructureLevelState,
    StructureState,
)


def _tail(items: Iterable[Any], limit: int) -> List[Any]:
    if limit <= 0:
        return list(items)
    seq = list(items)
    return seq[-limit:]


def _signal_snapshot(signal: Signal) -> Dict[str, Any]:
    return {
        "id": signal.id,
        "type": signal.type,
        "price": signal.price,
        "index": signal.index,
        "level": signal.level,
        "confidence": signal.confidence,
        "metadata": signal.metadata,
    }


def _segment_snapshot(segment) -> Dict[str, Any]:
    return {
        "id": segment.id,
        "direction": segment.direction,
        "start": segment.start_index,
        "end": segment.end_index,
        "level": segment.level,
        "pending_confirmation": segment.pending_confirmation,
        "feature_fractal": getattr(segment.feature_fractal, "type", None),
        "child_segments": getattr(segment, "metadata", {}).get("child_segment_ids", []),
        "nesting": getattr(segment, "metadata", {}).get("nesting"),
    }


def _stroke_snapshot(stroke) -> Dict[str, Any]:
    return {
        "id": stroke.id,
        "direction": stroke.direction,
        "start": stroke.start_bar_index,
        "end": stroke.end_bar_index,
        "level": stroke.level,
        "parent_segment_id": stroke.parent_segment_id,
        "parent_trend_id": stroke.parent_trend_id,
    }


def _trend_snapshot(trend) -> Dict[str, Any]:
    return {
        "id": trend.id,
        "direction": trend.direction,
        "start": trend.start_index,
        "end": trend.end_index,
        "level": trend.level,
        "parent_trend_id": trend.parent_trend_id,
        "child_trend_ids": trend.child_trend_ids,
    }

def build_segment_end_payload(segment) -> Dict[str, Any]:
    fractal = getattr(segment, "feature_fractal", None)
    feature_seq = [
        {"high": pen.high, "low": pen.low, "direction": pen.direction}
        for pen in (segment.feature_sequence[-6:] if getattr(segment, "feature_sequence", None) else [])
    ]
    return {
        "segment_id": getattr(segment, "id", None),
        "direction": getattr(segment, "direction", None),
        "end_confirmed": getattr(segment, "end_confirmed", True),
        "pending_confirmation": getattr(segment, "pending_confirmation", False),
        "feature_sequence_tail": feature_seq,
        "feature_fractal": {
            "type": getattr(fractal, "type", None),
            "has_gap": getattr(fractal, "has_gap", None),
            "pivot_price": getattr(fractal, "pivot_price", None),
        },
    }


def build_fugue_payload(summary: Dict[str, Any]) -> Dict[str, Any]:
    return summary


def build_momentum_payload(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return snapshot


def build_post_divergence_payload(outcome: PostDivergenceOutcome) -> Dict[str, Any]:
    return {
        "classification": outcome.classification,
        "overlap_rate": outcome.overlap_rate,
        "left_central": outcome.left_central,
        "new_trend_direction": outcome.new_trend_direction,
        "notes": outcome.notes,
        "evidence": dict(outcome.evidence),
    }


def build_level_snapshot(
    level_state: StructureLevelState,
    *,
    segment_limit: int = 3,
    stroke_limit: int = 4,
) -> Dict[str, Any]:
    segments = _tail(sorted(level_state.segments.values(), key=lambda seg: seg.end_index), segment_limit)
    strokes = _tail(sorted(level_state.strokes.values(), key=lambda st: st.end_bar_index), stroke_limit)
    trends = list(level_state.trends.values())

    return {
        "level": level_state.level,
        "active_trend_id": level_state.active_trend_id,
        "segments": [_segment_snapshot(seg) for seg in segments],
        "strokes": [_stroke_snapshot(st) for st in strokes],
        "trends": [_trend_snapshot(tr) for tr in trends],
        "signals": [_signal_snapshot(sig) for sig in level_state.signals],
        "metadata": level_state.metadata,
    }


def build_multilevel_summary(mappings: Sequence[MultiLevelMapping]) -> List[Dict[str, Any]]:
    summary: List[Dict[str, Any]] = []
    for mapping in mappings:
        summary.append(
            {
                "higher_level": mapping.higher_level,
                "lower_level": mapping.lower_level,
                "pen_map": mapping.pen_map,
                "segment_map": mapping.segment_map,
                "trend_map": mapping.trend_map,
                "metadata": mapping.metadata,
            }
        )
    return summary


def build_relation_summary(relation_matrix: Dict[str, Any]) -> Dict[str, Any]:
    if not relation_matrix:
        return {"resonance": False, "hedge": False, "dislocation": True, "summary": "暂无多级别对照信息"}
    return relation_matrix


def build_structure_payload(
    structure: StructureState,
    *,
    levels: Optional[Sequence[str]] = None,
    segment_limit: int = 3,
    stroke_limit: int = 4,
) -> Dict[str, Any]:
    level_order = list(levels) if levels else structure.levels or list(structure.level_states.keys())
    level_payload = []
    for level in level_order:
        state = structure.level_states.get(level)
        if state:
            level_payload.append(
                build_level_snapshot(
                    state,
                    segment_limit=segment_limit,
                    stroke_limit=stroke_limit,
                )
            )

    return {
        "levels": level_order,
        "level_details": level_payload,
        "relation_matrix": build_relation_summary(structure.relation_matrix),
        "multilevel": build_multilevel_summary(structure.multilevel_mappings),
        "metadata": structure.metadata,
    }


def build_position_payload(position: PositionState) -> Dict[str, Any]:
    return {
        "quantity": position.quantity,
        "avg_cost": position.avg_cost,
        "book_cost": position.book_cost,
        "initial_capital": position.initial_capital,
        "remaining_capital": position.remaining_capital,
        "withdrawn_capital": position.withdrawn_capital,
        "realized_profit": position.realized_profit,
        "initial_quantity": position.initial_quantity,
        "last_sell_qty": position.last_sell_qty,
        "stage": position.stage,
        "free_ride": position.free_ride,
        "cost_stage": getattr(position, "cost_stage", "INITIAL"),
        "initial_avg_cost": position.initial_avg_cost,
        "principal_recovered": position.principal_recovered,
        "cost_coverage_ratio": position.cost_coverage_ratio,
        "next_milestone": position.next_milestone,
        "cooldown_bars": position.cooldown_bars,
        "last_action": position.last_action,
        "margin_mode": position.margin_mode,
        "current_leverage": position.current_leverage,
        "liquidation_price": position.liquidation_price,
        "equity": position.equity,
    }


def build_synergy_payload(
    structure: StructureState,
    position: PositionState,
    *,
    extras: Optional[Dict[str, Any]] = None,
    levels: Optional[Sequence[str]] = None,
    ta_packet: Optional[Dict[str, Any]] = None,
    ta_focus: Optional[Dict[str, Any]] = None,
    performance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "structure": build_structure_payload(structure, levels=levels),
        "position": build_position_payload(position),
    }
    if extras:
        payload["extras"] = extras
    if ta_packet or ta_focus:
        payload["ta"] = {}
        if ta_packet:
            payload["ta"]["packet"] = ta_packet
        if ta_focus:
            payload["ta"]["focus"] = ta_focus
    if performance:
        payload["performance"] = performance
    return payload


def pretty_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)

