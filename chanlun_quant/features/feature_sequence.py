from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from chanlun_quant.types import Direction, FeatureFractal, Stroke


def intervals_overlap(a_low: float, a_high: float, b_low: float, b_high: float, tol: float = 0.0) -> bool:
    """Return True if two price ranges overlap (inclusive)."""
    if a_low > a_high:
        a_low, a_high = a_high, a_low
    if b_low > b_high:
        b_low, b_high = b_high, b_low
    return not (a_low > b_high + tol or b_low > a_high + tol)


def interval_contains(outer_low: float, outer_high: float, inner_low: float, inner_high: float, tol: float = 0.0) -> bool:
    """Return True if [inner_low, inner_high] is fully contained within [outer_low, outer_high]."""
    if outer_low > outer_high:
        outer_low, outer_high = outer_high, outer_low
    if inner_low > inner_high:
        inner_low, inner_high = inner_high, inner_low
    return (outer_low - tol) <= inner_low and (outer_high + tol) >= inner_high


def _is_top_fractal(a: Stroke, b: Stroke, c: Stroke) -> bool:
    return b.high > a.high and b.high > c.high and b.low > a.low and b.low > c.low


def _is_bottom_fractal(a: Stroke, b: Stroke, c: Stroke) -> bool:
    return b.low < a.low and b.low < c.low and b.high < a.high and b.high < c.high


@dataclass
class FeatureSequenceState:
    """Snapshot after a feature fractal is detected."""

    fractal: FeatureFractal
    sequence: List[Stroke]


class FeatureSequenceBuilder:
    """Maintain the reverse-direction stroke sequence inside a segment."""

    def __init__(self, gap_tolerance: float = 0.0) -> None:
        self._segment_direction: Optional[Direction] = None
        self._gap_tolerance = float(gap_tolerance)
        self._sequence: List[Stroke] = []
        self._last_state: Optional[FeatureSequenceState] = None

    def reset(self, segment_direction: Direction) -> None:
        self._segment_direction = segment_direction
        self._sequence.clear()
        self._last_state = None

    @property
    def direction(self) -> Optional[Direction]:
        return self._segment_direction

    def clear(self) -> None:
        self._sequence.clear()
        self._last_state = None

    def append(self, stroke: Stroke) -> Optional[FeatureSequenceState]:
        if self._segment_direction is None:
            raise ValueError("feature sequence builder not initialized with segment direction")
        if stroke.direction == self._segment_direction:
            raise ValueError("feature sequence expects opposite-direction strokes only")

        self._append_standard(stroke)
        state = self._detect_fractal()
        if state:
            self._last_state = state
        return state

    def snapshot(self) -> List[Stroke]:
        return list(self._sequence)

    def last_state(self) -> Optional[FeatureSequenceState]:
        return self._last_state

    def _append_standard(self, stroke: Stroke) -> None:
        seq = self._sequence
        while seq:
            last = seq[-1]
            if interval_contains(last.low, last.high, stroke.low, stroke.high):
                return
            if interval_contains(stroke.low, stroke.high, last.low, last.high):
                seq.pop()
                continue
            break
        seq.append(stroke)

    def _detect_fractal(self) -> Optional[FeatureSequenceState]:
        if len(self._sequence) < 3 or self._segment_direction is None:
            return None
        a, b, c = self._sequence[-3:]

        if self._segment_direction == "up":
            if not _is_top_fractal(a, b, c):
                return None
            has_gap = not intervals_overlap(a.low, a.high, b.low, b.high, self._gap_tolerance)
            fractal = FeatureFractal(
                type="top",
                has_gap=has_gap,
                pivot_price=b.high,
                pivot_index=b.end_bar_index,
                strokes=list(self._sequence),
            )
            return FeatureSequenceState(fractal=fractal, sequence=list(self._sequence))

        if self._segment_direction == "down":
            if not _is_bottom_fractal(a, b, c):
                return None
            has_gap = not intervals_overlap(a.low, a.high, b.low, b.high, self._gap_tolerance)
            fractal = FeatureFractal(
                type="bottom",
                has_gap=has_gap,
                pivot_price=b.low,
                pivot_index=b.end_bar_index,
                strokes=list(self._sequence),
            )
            return FeatureSequenceState(fractal=fractal, sequence=list(self._sequence))

        return None
