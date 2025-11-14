from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

SignalType = Literal["buy", "sell", "hold"]
Level = Literal["M1", "M5", "M15", "H1", "H4", "D1", "W1"]


@dataclass
class Signal:
    """Unified signal envelope carrying evidence and sizing hints."""

    level: Level
    kind: SignalType
    why: str
    refs: List[str]
    methods: List[str]
    weight: float = 1.0
    confidence: float = 0.6
    strength: float = 0.6
    entry_band: Optional[List[float]] = None
    stop_band: Optional[List[float]] = None
    take_band: Optional[List[float]] = None
    t_window: Optional[int] = None
    tags: Optional[List[str]] = None
    extras: Optional[Dict[str, Any]] = None


def pick_top_signals(signals: List[Signal], top_n: int = 6) -> List[Signal]:
    """Rank by weight * confidence * strength to surface the strongest candidates."""

    def _score(sig: Signal) -> float:
        return float(sig.weight or 0.0) * float(sig.confidence or 0.0) * float(sig.strength or 0.0)

    return sorted(signals, key=_score, reverse=True)[:top_n]


def same_direction(a: Signal, b: Signal) -> bool:
    if a.kind == "hold" or b.kind == "hold":
        return True
    return a.kind == b.kind
