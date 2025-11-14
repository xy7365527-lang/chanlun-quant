from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class LeverageCaps:
    L_exch_max: float
    L_cfg_max: float
    step: float
    mm: float  # maintenance margin rate
    buffer: float  # liquidation buffer ratio


def _round_down_to_step(x: float, step: float) -> float:
    if step <= 0:
        return x
    return max(step, math.floor(x / step) * step)


def estimate_liq_price(entry: float, side: str, L: float, mm: float, fee_buffer_bp: float = 5.0) -> float:
    fb = max(0.0, fee_buffer_bp) / 1e4
    side_lower = side.lower()

    if L <= 0 or entry <= 0:
        return entry

    leverage = max(float(L), 0.0)
    maintenance = max(float(mm), 0.0)
    exposure = min(0.99, maintenance * leverage)

    if side_lower == "long":
        return entry * max(1e-9, 1.0 - exposure) * max(0.0, 1.0 - fb)

    return entry * (1.0 + exposure) * (1.0 + fb)

def safe_leverage_cap_by_stop(entry: float, stop: float, side: str, caps: LeverageCaps) -> float:
    d_stop = abs(entry - stop) / max(entry, 1e-9)
    denom = caps.mm + d_stop / max(1e-9, (1.0 - caps.buffer))
    if denom <= 0:
        L = min(caps.L_exch_max, caps.L_cfg_max)
    else:
        L = min(1.0 / denom, caps.L_exch_max, caps.L_cfg_max)
    return max(caps.step, _round_down_to_step(L, caps.step))


def budget_leverage(remaining_capital: float, equity: float, entry: float, stop: float, cfg) -> float:
    d_stop = max(abs(entry - stop) / max(entry, 1e-9), cfg.min_stop_distance_pct)
    risk_budget = cfg.risk_per_trade_pct * (equity if equity else remaining_capital)
    if d_stop <= 0:
        return 1.0
    notional_target = risk_budget / d_stop
    if remaining_capital <= 0:
        return 1.0
    L = notional_target / remaining_capital
    return max(1.0, L)


def vol_adjust(mult_base: float, atr_norm: float, cfg) -> float:
    ratio = max(1e-9, atr_norm / max(1e-9, cfg.atr_vol_norm))
    damp = 1.0 / math.sqrt(ratio)
    mult = mult_base * damp
    return max(0.5, min(1.5, mult))


def combine_leverage(
    entry: float,
    stop: float,
    side: str,
    remaining_capital: float,
    equity: float,
    atr_norm: float,
    fusion_score: float,
    confidence: float,
    cfg,
) -> Dict[str, float]:
    caps = LeverageCaps(
        L_exch_max=cfg.exch_max_leverage,
        L_cfg_max=cfg.max_leverage_config,
        step=cfg.leverage_step,
        mm=cfg.exch_maint_margin,
        buffer=cfg.liq_buffer_ratio,
    )

    L_safe = safe_leverage_cap_by_stop(entry, stop, side, caps)
    L_budget = budget_leverage(remaining_capital, equity or remaining_capital, entry, stop, cfg)
    L0 = min(L_safe, L_budget, caps.L_exch_max, caps.L_cfg_max)

    fusion_clip = max(0.0, min(1.0, fusion_score))
    confidence_clip = max(0.0, min(1.0, confidence))
    mult_base = 0.5 + 0.5 * fusion_clip * confidence_clip
    mult_vol = vol_adjust(mult_base, atr_norm, cfg)
    L_suggest = max(1.0, min(L0, _round_down_to_step(L0 * mult_vol, caps.step)))

    return {
        "L_safe": float(L_safe),
        "L_budget": float(L_budget),
        "L0_cap": float(L0),
        "L_suggest": float(L_suggest),
    }


