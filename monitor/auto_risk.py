from __future__ import annotations

from ..core.envelope import Envelope
from .regime import detect_regime, recommend_child_ratio


def adjust_envelope(envelope: Envelope, highs, lows, closes, seg_cover: float) -> Envelope:
    """Adjust child_max_ratio heuristically based on detected volatility regime."""

    regime = detect_regime(highs, lows, closes, seg_cover)
    envelope.child_max_ratio = recommend_child_ratio(regime, envelope.child_max_ratio)
    return envelope
