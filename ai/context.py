from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from ..config import Config
from ..core.envelope import Envelope
from ..features.segment_index import SegmentIndex


def _last_n_by_level(
    items: Sequence[Any],
    level: str,
    n: int,
    key: Callable[[Any], Any] = lambda x: getattr(x, "i1", 0),
) -> List[Any]:
    """筛选指定级别的末尾 n 个元素。"""
    filtered = [item for item in items if getattr(item, "level", None) == level]
    filtered.sort(key=key)
    return filtered[-n:] if n > 0 else []


def _segments_brief(seg_idx: SegmentIndex, level: str, n: int = 2) -> List[Dict[str, Any]]:
    segs = _last_n_by_level(list(seg_idx.rsg.segments.values()), level, n)
    result: List[Dict[str, Any]] = []
    for seg in segs:
        result.append(
            {
                "id": seg.id,
                "i0": seg.i0,
                "i1": seg.i1,
                "trend_state": seg.trend_state,
                "feature_seq_tail": seg.feature_seq[-6:] if seg.feature_seq else [],
                "zhongshu": seg.zhongshu or {},
                "divergence": seg.divergence,
                "macd": {
                    "area_dir": seg.macd_area_dir,
                    "area_abs": seg.macd_area_abs,
                    "dens": seg.macd_dens,
                    "eff_price": seg.macd_eff_price,
                    "peak_pos": seg.macd_peak_pos,
                    "peak_neg": seg.macd_peak_neg,
                },
                "mmds": seg.mmds,
                "children": seg_idx.map_to_lower(level, seg.id),
            }
        )
    return result


def _pens_brief(seg_idx: SegmentIndex, level: str, n: int = 3) -> List[Dict[str, Any]]:
    pens = _last_n_by_level(list(seg_idx.rsg.pens.values()), level, n)
    result: List[Dict[str, Any]] = []
    for pen in pens:
        result.append(
            {
                "id": pen.id,
                "i0": pen.i0,
                "i1": pen.i1,
                "direction": pen.direction,
                "macd": {
                    "area_pos": pen.macd_area_pos,
                    "area_neg": pen.macd_area_neg,
                    "area_abs": pen.macd_area_abs,
                    "area_net": pen.macd_area_net,
                    "dens": pen.macd_dens,
                    "eff_price": pen.macd_eff_price,
                    "peak_pos": pen.macd_peak_pos,
                    "peak_neg": pen.macd_peak_neg,
                },
                "mmds": pen.mmds,
            }
        )
    return result


def build_costzero_context(
    seg_idx: SegmentIndex,
    ledger: Mapping[str, Any],
    envelope: Envelope,
    cfg: Config,
    levels: Optional[Sequence[str]] = None,
    per_level_segments: int = 2,
    per_level_pens: int = 3,
) -> Dict[str, Any]:
    """将 RSG/SegmentIndex + ledger/envelope/cfg 打包为 LLM 可消费的最小上下文。"""
    lvls = list(levels) if levels is not None else list(seg_idx.rsg.levels)
    structure: List[Dict[str, Any]] = []
    for level in lvls:
        structure.append(
            {
                "level": level,
                "segments": _segments_brief(seg_idx, level, per_level_segments),
                "pens": _pens_brief(seg_idx, level, per_level_pens),
            }
        )
    context = {
        "symbol": seg_idx.rsg.symbol,
        "levels": lvls,
        "structure": structure,
        "ledger": {
            "core_qty": float(ledger.get("core_qty", 0.0)),
            "remaining_cost": float(ledger.get("remaining_cost", 0.0)),
            "free_ride_qty": float(ledger.get("free_ride_qty", 0.0)),
            "pen": ledger.get("pen", {}),
            "segment": ledger.get("segment", {}),
        },
        "envelope": {
            "net_direction": envelope.net_direction,
            "child_max_ratio": envelope.child_max_ratio,
            "forbid_zone": envelope.forbid_zone,
        },
        "constraints": {
            "r_pen": cfg.r_pen,
            "r_seg": cfg.r_seg,
            "r_trend": getattr(cfg, "r_trend", 0.90),
            "k_grid": cfg.k_grid,
            "min_step_mult": cfg.min_step_mult,
            "fee_slippage_hint": "Δprice must exceed fee+slippage; if uncertain, HOLD.",
        },
        "goal": "Reduce remaining_cost to 0 without changing net direction; one-cycle net plan only.",
    }
    core_qty = float(ledger.get("core_qty", 0.0))
    used_child_capacity = (
        abs(float(ledger.get("pen", {}).get("qty", 0.0)))
        + abs(float(ledger.get("segment", {}).get("qty", 0.0)))
    )
    safe_core = core_qty if core_qty != 0 else 1e-9
    context["meta"] = {
        "levels_selected_reason": seg_idx.rsg.build_info.get("level_selector_reason", ""),
        "latest_price": ledger.get("latest_price"),
        "used_child_capacity_est": used_child_capacity / abs(safe_core),
    }
    # 如需提供明确手续费/滑点，可视情况将 fee/slippage 信息补入 constraints
    # context["constraints"]["fee_bps"] = getattr(cfg, "fee_bps", None)
    # context["constraints"]["slippage_bps"] = getattr(cfg, "slippage_bps", None)
    if ledger.get("_pre_signals"):
        context["pre_signals"] = ledger["_pre_signals"]
    return context
