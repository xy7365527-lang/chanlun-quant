"""K-line normalization and containment handling."""

from __future__ import annotations

from typing import List

from chanlun_quant.types import Bar

DirectionType = str


def merge_containment(bars: list[Bar]) -> list[Bar]:
    """Merge inclusion relationships among consecutive bars."""
    merged: list[Bar] = []
    for bar in bars:
        current = bar
        while merged:
            last = merged[-1]
            if _is_inside(current, last):
                direction = _resolve_direction(merged[:-1], last, current)
                current = _merge_bars(last, current, direction)
                merged.pop()
                continue
            if _is_inside(last, current):
                merged.pop()
                continue
            break
        merged.append(current)
    return merged


def normalize(bars: list[Bar]) -> list[Bar]:
    """Normalize bars by resolving containment chains."""
    return merge_containment(list(bars))


def _is_inside(candidate: Bar, reference: Bar) -> bool:
    return candidate.high <= reference.high and candidate.low >= reference.low


def _resolve_direction(history: List[Bar], reference: Bar, candidate: Bar) -> DirectionType:
    if candidate.high >= reference.high:
        return "up"
    if candidate.low <= reference.low:
        return "down"
    if history:
        prev = history[-1]
        if reference.high >= prev.high:
            return "up"
        if reference.low <= prev.low:
            return "down"
    return "up" if reference.close >= reference.open else "down"


def _merge_bars(reference: Bar, candidate: Bar, direction: DirectionType) -> Bar:
    if direction == "down":
        high = min(reference.high, candidate.high)
        low = min(reference.low, candidate.low)
    else:
        high = max(reference.high, candidate.high)
        low = max(reference.low, candidate.low)

    return Bar(
        timestamp=candidate.timestamp,
        open=candidate.open,
        high=high,
        low=low,
        close=candidate.close,
        volume=candidate.volume,
        index=candidate.index,
        level=candidate.level,
    )
