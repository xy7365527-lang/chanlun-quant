from __future__ import annotations

from typing import Dict, List, Tuple

from ..features.segment_index import SegmentIndex
from .pen_agent import PenAgent
from .segment_agent import SegmentAgent
from .signal import Level, Signal, pick_top_signals
from .trend_agent import TrendAgent
from .scorer import score_signals


def run_agents(
    levels: List[Level],
    seg_idx: SegmentIndex,
    last_price: float,
) -> Tuple[List[Signal], List[Dict[str, float]]]:
    """运行多级别 Agents，返回信号与 envelope_update 建议集合。"""
    signals: List[Signal] = []
    envelope_suggestions: List[Dict[str, float]] = []

    for level in levels:
        signals.extend(PenAgent(level).evaluate(seg_idx, last_price))
        signals.extend(SegmentAgent(level).evaluate(seg_idx))

        trend_signals = TrendAgent(level).evaluate(seg_idx)
        for sig in trend_signals:
            if sig.extras and "envelope_update" in sig.extras:
                envelope_suggestions.append(sig.extras["envelope_update"])
        signals.extend([sig for sig in trend_signals if not sig.extras])

    signals = score_signals(signals, seg_idx)
    signals = pick_top_signals(signals, top_n=6)
    return signals, envelope_suggestions

