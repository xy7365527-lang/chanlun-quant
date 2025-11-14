from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from chanlun_quant.analysis.multilevel import analyze_relation_matrix, build_multilevel_mapping
from chanlun_quant.config import Config
from chanlun_quant.types import (
    Bar,
    Fractal,
    MultiLevelMapping,
    Signal,
    Stroke,
    StructureLevelState,
    StructureState,
    Segment,
    Trend,
)


_DEFAULT_DRAWDOWN = 0.06


def _ensure_indices(bars: List[Bar]) -> None:
    for idx, bar in enumerate(sorted(bars, key=lambda b: b.timestamp)):
        bar.index = idx


def _detect_fractals(bars: List[Bar], level: str) -> List[Fractal]:
    if len(bars) < 2:
        return [
            Fractal(type="bottom", index=bars[0].index, price=bars[0].low, bar_index=bars[0].index, level=level),
            Fractal(type="top", index=bars[-1].index, price=bars[-1].high, bar_index=bars[-1].index, level=level),
        ]

    candidates: List[Fractal] = []
    for idx in range(1, len(bars) - 1):
        prev_bar, bar, next_bar = bars[idx - 1], bars[idx], bars[idx + 1]
        if bar.high >= prev_bar.high and bar.high >= next_bar.high and bar.low >= prev_bar.low and bar.low >= next_bar.low:
            candidates.append(Fractal(type="top", index=idx, price=bar.high, bar_index=bar.index, level=level))
        elif bar.low <= prev_bar.low and bar.low <= next_bar.low and bar.high <= prev_bar.high and bar.high <= next_bar.high:
            candidates.append(Fractal(type="bottom", index=idx, price=bar.low, bar_index=bar.index, level=level))

    if not candidates:
        first_bar = bars[0]
        last_bar = bars[-1]
        return [
            Fractal(type="bottom", index=first_bar.index, price=first_bar.low, bar_index=first_bar.index, level=level),
            Fractal(type="top", index=last_bar.index, price=last_bar.high, bar_index=last_bar.index, level=level),
        ]

    filtered: List[Fractal] = []
    for frac in candidates:
        if not filtered:
            filtered.append(frac)
            continue
        last = filtered[-1]
        if frac.type == last.type:
            if frac.type == "top" and frac.price >= last.price:
                filtered[-1] = frac
            elif frac.type == "bottom" and frac.price <= last.price:
                filtered[-1] = frac
            continue
        filtered.append(frac)

    first = filtered[0]
    if first.type != "bottom":
        first_bar = bars[0]
        filtered.insert(0, Fractal(type="bottom", index=first_bar.index, price=first_bar.low, bar_index=first_bar.index, level=level))

    last = filtered[-1]
    expected_last_type = "top" if last.type == "bottom" else "bottom"
    last_bar = bars[-1]
    if last.type != expected_last_type or last.bar_index != last_bar.index:
        last_price = last_bar.high if expected_last_type == "top" else last_bar.low
        filtered.append(Fractal(type=expected_last_type, index=last_bar.index, price=last_price, bar_index=last_bar.index, level=level))

    return filtered


def _build_strokes(fractals: List[Fractal], bars: List[Bar], level: str) -> List[Stroke]:
    if len(fractals) < 2:
        return []
    bars_by_index = {bar.index: bar for bar in bars}
    strokes: List[Stroke] = []
    for idx in range(1, len(fractals)):
        start = fractals[idx - 1]
        end = fractals[idx]
        if start.type == end.type:
            continue
        direction = "up" if end.price >= start.price else "down"
        start_idx = min(start.bar_index, end.bar_index)
        end_idx = max(start.bar_index, end.bar_index)
        sub = [bar for bar in bars if start_idx <= bar.index <= end_idx]
        high = max((bar.high for bar in sub), default=max(start.price, end.price))
        low = min((bar.low for bar in sub), default=min(start.price, end.price))
        start_time = bars_by_index[start_idx].timestamp if start_idx in bars_by_index else bars[0].timestamp
        end_time = bars_by_index[end_idx].timestamp if end_idx in bars_by_index else bars[-1].timestamp
        strokes.append(
            Stroke(
                start_fractal=start,
                end_fractal=end,
                direction=direction,  # type: ignore[arg-type]
                high=high,
                low=low,
                start_bar_index=start_idx,
                end_bar_index=end_idx,
                id=f"{level}:stroke:{start_idx}-{end_idx}",
                level=level,
                start_time=start_time,
                end_time=end_time,
            )
        )
    return strokes


def _make_segment(strokes: List[Stroke], direction: str, level: str, index: int) -> Segment:
    start_idx = min(strokes[0].start_bar_index, strokes[0].end_bar_index)
    end_idx = max(strokes[-1].start_bar_index, strokes[-1].end_bar_index)
    start_time = strokes[0].start_time
    end_time = strokes[-1].end_time
    return Segment(
        strokes=list(strokes),
        direction=direction,  # type: ignore[arg-type]
        start_index=start_idx,
        end_index=end_idx,
        id=f"{level}:segment:{index}",
        level=level,
        start_time=start_time,
        end_time=end_time,
        pens=list(strokes),
        metadata={},
    )


def _build_segments(strokes: List[Stroke], level: str) -> List[Segment]:
    if not strokes:
        return []
    segments: List[Segment] = []
    current: List[Stroke] = [strokes[0]]
    current_dir = strokes[0].direction

    for stroke in strokes[1:]:
        if stroke.direction == current_dir:
            current.append(stroke)
            continue
        segments.append(_make_segment(current, current_dir, level, len(segments)))
        current = [stroke]
        current_dir = stroke.direction

    if current:
        segments.append(_make_segment(current, current_dir, level, len(segments)))
    return segments


def _make_trend(segments: List[Segment], direction: str, level: str, index: int) -> Trend:
    start_idx = segments[0].start_index
    end_idx = segments[-1].end_index
    start_time = segments[0].start_time
    end_time = segments[-1].end_time
    return Trend(
        direction=direction,  # type: ignore[arg-type]
        segments=list(segments),
        start_index=start_idx,
        end_index=end_idx,
        level=level,
        id=f"{level}:trend:{index}",
        start_time=start_time,
        end_time=end_time,
    )


def _build_trends(segments: List[Segment], level: str) -> List[Trend]:
    if not segments:
        return []
    trends: List[Trend] = []
    current: List[Segment] = [segments[0]]
    current_dir = segments[0].direction

    for segment in segments[1:]:
        if segment.direction == current_dir:
            current.append(segment)
            continue
        trends.append(_make_trend(current, current_dir, level, len(trends)))
        current = [segment]
        current_dir = segment.direction

    if current:
        trends.append(_make_trend(current, current_dir, level, len(trends)))
    return trends


def _generate_signals(strokes: List[Stroke], bars: List[Bar], level: str) -> List[Signal]:
    if len(strokes) < 2 or not bars:
        return []
    latest_bar = bars[-1]
    latest_idx = latest_bar.index
    signals: List[Signal] = []
    last = strokes[-1]
    prev = strokes[-2]
    if last.direction == "up" and prev.direction == "down":
        signals.append(
            Signal(
                type="BUY1",
                price=latest_bar.close,
                index=latest_idx,
                level=level,
                id=f"{level}:sig:{latest_idx}:buy1",
                source="structure",
            )
        )
    elif last.direction == "down" and prev.direction == "up":
        signals.append(
            Signal(
                type="SELL1",
                price=latest_bar.close,
                index=latest_idx,
                level=level,
                id=f"{level}:sig:{latest_idx}:sell1",
                source="structure",
            )
        )
    return signals


def _trend_direction(trend: Optional[Trend]) -> str:
    if not trend:
        return "flat"
    return trend.direction or "flat"


def _max_drawdown(bars: List[Bar]) -> float:
    if not bars:
        return 0.0
    max_close = bars[0].close
    drawdown = 0.0
    for bar in bars:
        max_close = max(max_close, bar.close)
        if max_close > 0:
            drawdown = min(drawdown, (bar.close - max_close) / max_close)
    return abs(drawdown)


@dataclass
class AnalysisResult:
    structure: StructureState
    extras: Dict[str, Any]


class StructureAnalyzer:
    """
    Minimal ChanLun-inspired structure analyzer.

    The implementation focuses on producing a consistent ``StructureState`` so
    that downstream modules (LLM prompts, trade rhythm engine, etc.) receive
    coherent data, while keeping the computational model lightweight.
    """

    def __init__(self, levels: Sequence[str], *, config: Optional[Config] = None, drawdown_exit: float = _DEFAULT_DRAWDOWN) -> None:
        if not levels:
            raise ValueError("StructureAnalyzer requires at least one level")
        self.levels = list(levels)
        self.config = config or Config(levels=tuple(levels))
        self.drawdown_exit = max(drawdown_exit, 0.0)

    def __call__(self, bars_by_level: Dict[str, List[Bar]], previous: Optional[StructureState] = None) -> Tuple[StructureState, Dict[str, Any]]:
        return self.analyze(bars_by_level, previous)

    # pylint: disable=unused-argument
    def analyze(self, bars_by_level: Dict[str, List[Bar]], previous: Optional[StructureState] = None) -> Tuple[StructureState, Dict[str, Any]]:
        level_states: Dict[str, StructureLevelState] = {}
        trend_summary: Dict[str, str] = {}
        signals_by_level: Dict[str, List[Signal]] = {}

        for level in self.levels:
            bars = list(bars_by_level.get(level, []))
            if not bars:
                continue
            _ensure_indices(bars)
            fractals = _detect_fractals(bars, level)
            strokes = _build_strokes(fractals, bars, level)
            segments = _build_segments(strokes, level)
            trends = _build_trends(segments, level)
            signals = _generate_signals(strokes, bars, level)

            active_trend = trends[-1] if trends else None
            trend_summary[level] = _trend_direction(active_trend)

            state = StructureLevelState(
                level=level,
                strokes={stroke.id: stroke for stroke in strokes},
                segments={segment.id: segment for segment in segments},
                trends={trend.id: trend for trend in trends},
                active_trend_id=active_trend.id if active_trend else None,
                signals=signals,
                metadata={"fractals": fractals},
            )
            level_states[level] = state
            if signals:
                signals_by_level[level] = signals

        structure = StructureState(
            levels=list(self.levels),
            level_states=level_states,
        )

        # Aggregate trend references and signals at the top level
        structure.trends = {}
        structure.signals = {}
        for level, state in level_states.items():
            if state.active_trend_id and state.active_trend_id in state.trends:
                structure.trends[level] = state.trends[state.active_trend_id]
            elif state.trends:
                structure.trends[level] = next(iter(state.trends.values()))
            if state.signals:
                structure.signals[level] = state.signals

        # Build multi-level mapping (low -> high)
        multilevel: List[MultiLevelMapping] = []
        if len(self.levels) >= 2:
            for idx in range(1, len(self.levels)):
                low = self.levels[idx - 1]
                high = self.levels[idx]
                low_state = level_states.get(low)
                high_state = level_states.get(high)
                if not low_state or not high_state:
                    continue
                multilevel.append(
                    build_multilevel_mapping(
                        low_level=low,
                        high_level=high,
                        low_strokes=list(low_state.strokes.values()),
                        high_strokes=list(high_state.strokes.values()),
                        low_segments=list(low_state.segments.values()),
                        high_segments=list(high_state.segments.values()),
                        low_trends=list(low_state.trends.values()),
                        high_trends=list(high_state.trends.values()),
                    )
                )
        structure.multilevel_mappings = multilevel
        structure.relation_matrix = analyze_relation_matrix(level_states, list(self.levels))

        # Determine primary signal
        primary_level: Optional[str] = None
        primary_signal = "HOLD"
        for level in self.levels:
            level_signals = signals_by_level.get(level)
            if not level_signals:
                continue
            primary_signal = level_signals[-1].type
            primary_level = level
            break

        # Risk override: strong downside drawdown
        lowest_level = self.levels[0]
        lowest_bars = list(bars_by_level.get(lowest_level, []))
        price_hint = lowest_bars[-1].close if lowest_bars else 0.0
        if lowest_bars:
            drawdown = _max_drawdown(lowest_bars)
            peak_close = max(bar.close for bar in lowest_bars)
            last_close = lowest_bars[-1].close
            if drawdown >= self.drawdown_exit and last_close < peak_close:
                primary_signal = "SELL_ALL"
                primary_level = lowest_level

        extras = {
            "signal": primary_signal,
            "primary_level": primary_level,
            "price": price_hint,
            "level_signals": {level: [sig.type for sig in sigs] for level, sigs in signals_by_level.items()},
            "trend_directions": trend_summary,
            "relation_summary": structure.relation_matrix.get("summary"),
        }

        return structure, extras


def build_default_analyzer(config: Optional[Config] = None) -> StructureAnalyzer:
    config = config or Config()
    return StructureAnalyzer(config.levels, config=config)

