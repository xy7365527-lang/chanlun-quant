from __future__ import annotations

from typing import List

from ..features.market_stats import natr


def detect_regime(highs: List[float], lows: List[float], closes: List[float], seg_cover: float) -> str:
    """Classify a coarse volatility/structure regime based on nATR and zhongshu cover ratio."""

    na = natr(highs, lows, closes, 14)
    if na < 0.006 and seg_cover > 0.12:
        return "range_lowvol"
    if na < 0.006 and seg_cover <= 0.12:
        return "drift"
    if na >= 0.02:
        return "volatile"
    return "trend"


def recommend_child_ratio(regime: str, base: float = 0.35) -> float:
    if regime == "range_lowvol":
        return min(0.50, base + 0.10)
    if regime == "volatile":
        return max(0.20, base - 0.10)
    return base
