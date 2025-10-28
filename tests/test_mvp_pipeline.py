from __future__ import annotations

import math
from typing import Dict, List

from chanlun_quant.ai.interface import ChanLLM
from chanlun_quant.config import Config
from chanlun_quant.core.engine import Engine
from chanlun_quant.features.segment_index import SegmentIndex
from chanlun_quant.rsg.build import build_level_pens_segments, build_multi_levels
from chanlun_quant.strategy.cost_zero_baseline import CostZeroBaseline


class DummyFeed:
    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, List[float]]] = {}

    def get_bars(self, symbol: str, level: str) -> Dict[str, List[float]]:
        key = f"{symbol}:{level}"
        if key in self._cache:
            return self._cache[key]
        n = 120
        close: List[float] = []
        for i in range(n):
            phase = i % 6
            if phase == 0:
                close.append(0.0)
            elif phase == 1:
                close.append(1.0)
            elif phase == 2:
                close.append(0.2)
            elif phase == 3:
                close.append(0.0)
            elif phase == 4:
                close.append(-1.0)
            else:
                close.append(-0.2)
        high = [c + 0.1 for c in close]
        low = [c - 0.1 for c in close]
        macd = [math.sin(i / 6.0) for i in range(n)]
        payload = {"close": close, "high": high, "low": low, "macd": macd}
        self._cache[key] = payload
        return payload

    def get_atr(self, symbol: str, level: str) -> float:
        return 1.0


def test_build_level_pens_segments_basic() -> None:
    feed = DummyFeed()
    data = feed.get_bars("X", "M15")
    pens, segs, edges = build_level_pens_segments(
        bars=[
            {"close": c, "high": h, "low": l}
            for c, h, l in zip(data["close"], data["high"], data["low"])
        ],
        level="M15",
        macd_hist=data["macd"],
    )
    assert pens, "expected non-empty pens list"
    assert segs, "expected non-empty segments list"
    assert edges, "expected segment-pen edges"


def test_build_multi_levels_and_index() -> None:
    feed = DummyFeed()
    level_bars = {
        "M15": feed.get_bars("X", "M15"),
        "H1": feed.get_bars("X", "H1"),
        "D1": feed.get_bars("X", "D1"),
    }
    rsg = build_multi_levels(level_bars)
    idx = SegmentIndex(rsg)
    assert idx.parent, "parent mapping should not be empty"
    any_segment = next(iter(rsg.segments.values()))
    assert hasattr(any_segment, "divergence")
    divergence_flag = idx.seg_area_divergence(any_segment.level, any_segment.id)
    assert isinstance(divergence_flag, bool)


def test_baseline_and_engine() -> None:
    feed = DummyFeed()
    level_bars = {
        "M15": feed.get_bars("X", "M15"),
        "H1": feed.get_bars("X", "H1"),
        "D1": feed.get_bars("X", "D1"),
    }
    rsg = build_multi_levels(level_bars)
    idx = SegmentIndex(rsg)
    plan = CostZeroBaseline().propose(idx, last_price=1.0)
    assert isinstance(plan.proposals, list)

    cfg = Config(use_auto_levels=False, use_cost_zero_ai=False)
    engine = Engine(cfg=cfg, llm=ChanLLM(client=None))

    orders = engine.run_cycle(
        symbol="X",
        datafeed=feed,
        last_price=1.0,
        ledger={"remaining_cost": 1000.0, "risk_ctx": {"min_step": 1.0}},
    )
    assert isinstance(orders, list)
    for order in orders:
        assert isinstance(order, dict)
