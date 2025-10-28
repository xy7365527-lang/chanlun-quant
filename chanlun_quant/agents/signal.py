from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

SignalType = Literal["buy", "sell", "hold"]
Level = Literal["M1", "M5", "M15", "H1", "H4", "D1", "W1"]


@dataclass
class Signal:
    """统一信号：仅表达“候选动作意图”，不含下单规模。"""

    level: Level
    kind: SignalType  # buy/sell/hold
    why: str
    refs: List[str]
    methods: List[str]
    weight: float = 1.0
    extras: Optional[Dict[str, Any]] = None


def pick_top_signals(signals: List[Signal], top_n: int = 4) -> List[Signal]:
    """按权重降序选前 N 条，用于降噪。"""
    return sorted(signals, key=lambda sig: sig.weight, reverse=True)[:top_n]


def same_direction(a: Signal, b: Signal) -> bool:
    """判定信号是否方向一致（含 HOLD 视为兼容）。"""
    if a.kind == "hold" or b.kind == "hold":
        return True
    return a.kind == b.kind

