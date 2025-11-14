from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pytest

from chanlun_quant.ai.interface import ChanLLM, LLMClient
from chanlun_quant.broker.interface import SimulatedBroker
from chanlun_quant.config import Config
from chanlun_quant.datafeed.interface import DataFeed
from chanlun_quant.runtime.live_loop import LiveTradingLoop
from chanlun_quant.strategy.trade_rhythm import Action, TradeRhythmEngine
from chanlun_quant.types import (
    Bar,
    FeatureFractal,
    Fractal,
    MultiLevelMapping,
    Segment,
    Signal,
    StructureLevelState,
    StructureState,
    Stroke,
    Trend,
)
from chanlun_quant.ai.trading_agents import ResearchItem, ResearchPacket


class StubDataFeed(DataFeed):
    def __init__(self, levels: Tuple[str, ...]) -> None:
        base = datetime(2024, 1, 1)
        self.data: Dict[str, List[Bar]] = {}
        for level in levels:
            bars = []
            for idx in range(3):
                bars.append(
                    Bar(
                        timestamp=base + timedelta(minutes=idx),
                        open=10.0 + idx,
                        high=10.5 + idx,
                        low=9.5 + idx,
                        close=10.2 + idx,
                        volume=1_000 + idx,
                        index=idx,
                        level=level,
                    )
                )
            self.data[level] = bars

    def get_bars(self, level: str, lookback: int = 300) -> List[Bar]:
        return list(self.data.get(level, []))


class OscillatingFeed(DataFeed):
    def __init__(self, level: str) -> None:
        base = datetime(2024, 1, 1, 9, 30)
        prices = [10.0, 9.6, 9.4, 9.9, 10.5, 10.2]
        self.bars: Dict[str, List[Bar]] = {
            level: [
                Bar(
                    timestamp=base + timedelta(minutes=idx * 5),
                    open=price,
                    high=price + 0.4,
                    low=price - 0.4,
                    close=price,
                    volume=1_000 + idx,
                    index=idx,
                    level=level,
                )
                for idx, price in enumerate(prices)
            ]
        }

    def get_bars(self, level: str, lookback: int = 300) -> List[Bar]:
        return list(self.bars[level])


def _build_level_state(level: str) -> StructureLevelState:
    frac_start = Fractal(type="bottom", index=0, price=10.0, bar_index=0, level=level)
    frac_end = Fractal(type="top", index=1, price=11.0, bar_index=1, level=level)
    stroke = Stroke(
        start_fractal=frac_start,
        end_fractal=frac_end,
        direction="up",
        high=11.0,
        low=10.0,
        start_bar_index=0,
        end_bar_index=1,
        id=f"{level}:stroke",
        level=level,
    )
    segment = Segment(
        strokes=[stroke],
        direction="up",
        start_index=0,
        end_index=1,
        level=level,
        id=f"{level}:segment",
        feature_fractal=FeatureFractal(type="top", has_gap=False, pivot_price=11.0, pivot_index=1),
        metadata={"nesting": {"time_cover_count": 1}},
    )
    trend = Trend(
        direction="up",
        segments=[segment],
        start_index=0,
        end_index=1,
        level=level,
        id=f"{level}:trend",
    )
    signal = Signal(type="BUY1", price=10.5, index=1, level=level, id="sig-1")
    return StructureLevelState(
        level=level,
        strokes={stroke.id: stroke},
        segments={segment.id: segment},
        trends={trend.id: trend},
        active_trend_id=trend.id,
        signals=[signal],
    )


def _analyzer_with_signal(signal: str) -> Tuple[StructureState, Dict[str, object]]:
    level = "5m"
    level_state = _build_level_state(level)
    mapping = MultiLevelMapping(higher_level="30m", lower_level="5m")
    structure = StructureState(
        levels=[level],
        level_states={level: level_state},
        multilevel_mappings=[mapping],
        relation_matrix={"summary": "mock"},
    )
    extras = {"signal": signal, "price": 10.5}
    return structure, extras


class _StubTAManager:
    def __init__(self, packet: ResearchPacket) -> None:
        self._packet = packet
        self.enabled = True

    def get_research(self, symbol: str, structure_packet: Dict[str, object], stage: str):
        return self._packet, self._packet.get(symbol)


def test_live_loop_executes_trade_without_llm() -> None:
    cfg = Config(levels=("5m",), initial_buy_quantity=100.0)
    datafeed = StubDataFeed(cfg.levels)
    trade_engine = TradeRhythmEngine()
    broker = SimulatedBroker()

    def analyzer(snapshot, previous):
        return _analyzer_with_signal("BUY1")

    loop = LiveTradingLoop(
        config=cfg,
        datafeed=datafeed,
        analyzer=analyzer,
        trade_engine=trade_engine,
        broker=broker,
        llm=None,
        sleep_fn=lambda _: None,
    )

    outcome = loop.run_step()
    assert outcome.signal == "BUY1"
    assert outcome.order_result is not None
    assert broker.last_order is not None
    assert trade_engine.get_holding_manager().state.quantity > 0


def test_live_loop_respects_llm_hold() -> None:
    cfg = Config(levels=("5m",), initial_buy_quantity=100.0, use_llm=True)
    datafeed = StubDataFeed(cfg.levels)
    trade_engine = TradeRhythmEngine()
    broker = SimulatedBroker()

    client = LLMClient(mock_response={"action": "hold", "reason": "wait"})
    llm = ChanLLM(client=client)

    def analyzer(snapshot, previous):
        return _analyzer_with_signal("SELL1")

    loop = LiveTradingLoop(
        config=cfg,
        datafeed=datafeed,
        analyzer=analyzer,
        trade_engine=trade_engine,
        broker=broker,
        llm=llm,
        sleep_fn=lambda _: None,
    )

    outcome = loop.run_step()
    assert outcome.signal == "HOLD"
    assert outcome.order_result is None


def test_live_loop_llm_exit_maps_to_sell_all() -> None:
    cfg = Config(levels=("5m",), initial_buy_quantity=100.0, use_llm=True)
    datafeed = StubDataFeed(cfg.levels)
    trade_engine = TradeRhythmEngine()
    broker = SimulatedBroker()

    # Seed initial position so SELL_ALL has effect
    trade_engine.on_signal("BUY1", 10.0, cfg)
    trade_engine.get_holding_manager().buy(10.0, cfg.initial_buy_quantity, is_initial_buy=True)

    client = LLMClient(mock_response={"action": "exit", "quantity": cfg.initial_buy_quantity, "reason": "risk"})
    llm = ChanLLM(client=client)

    def analyzer(snapshot, previous):
        return _analyzer_with_signal("BUY1")

    loop = LiveTradingLoop(
        config=cfg,
        datafeed=datafeed,
        analyzer=analyzer,
        trade_engine=trade_engine,
        broker=broker,
        llm=llm,
        sleep_fn=lambda _: None,
    )

    outcome = loop.run_step()
    assert outcome.signal == "SELL_ALL"
    assert outcome.order_result is not None
    assert outcome.order_result.action == Action.SELL_ALL.value


def test_live_loop_with_default_analyzer_builds_structure() -> None:
    level = "5m"
    cfg = Config(levels=(level,), initial_buy_quantity=0.0)
    datafeed = OscillatingFeed(level)
    trade_engine = TradeRhythmEngine()
    broker = SimulatedBroker()

    loop = LiveTradingLoop(
        config=cfg,
        datafeed=datafeed,
        analyzer=None,
        trade_engine=trade_engine,
        broker=broker,
        llm=None,
        sleep_fn=lambda _: None,
    )

    outcome = loop.run_step()
    assert outcome.structure.levels == [level]
    assert outcome.signal in {"HOLD", "BUY1", "SELL1", "SELL_ALL"}
    assert outcome.action_plan["stage"] == trade_engine.get_current_stage().value


def test_live_loop_ta_blocks_initial_buy() -> None:
    cfg = Config(
        symbol="XYZ",
        levels=("5m",),
        initial_buy_quantity=80.0,
        ta_enabled=True,
        ta_score_threshold=0.6,
        ta_gate_mode="hard",
    )
    datafeed = StubDataFeed(cfg.levels)
    trade_engine = TradeRhythmEngine()
    broker = SimulatedBroker()

    blocking_item = ResearchItem(
        symbol="XYZ",
        score=0.4,
        recommendation="ignore",
        reason="Fundamental red flag",
        ta_gate=False,
        risk_mult=0.0,
        L_mult=0.0,
        kill_switch=True,
        risk_flags=["earnings"],
    )
    packet = ResearchPacket(analysis=[blocking_item], top_picks=[], generated_at=datetime.utcnow())

    loop = LiveTradingLoop(
        config=cfg,
        datafeed=datafeed,
        analyzer=lambda snapshot, previous: _analyzer_with_signal("BUY1"),
        trade_engine=trade_engine,
        broker=broker,
        llm=None,
    )
    loop.ta_manager = _StubTAManager(packet)

    outcome = loop.run_step()

    assert outcome.action_plan["action"] == Action.HOLD
    assert outcome.action_plan["quantity"] == 0.0
    assert outcome.action_plan["ta_influence"]["blocked"] is True
    assert "kill_switch" in outcome.action_plan["ta_influence"]["gate_reasons"]


def test_live_loop_ta_adjusts_quantity_via_risk_mult() -> None:
    cfg = Config(
        symbol="XYZ",
        levels=("5m",),
        initial_buy_quantity=50.0,
        ta_enabled=True,
        ta_score_threshold=0.5,
    )
    datafeed = StubDataFeed(cfg.levels)
    trade_engine = TradeRhythmEngine()
    broker = SimulatedBroker()

    approving_item = ResearchItem(
        symbol="XYZ",
        score=0.9,
        recommendation="buy",
        reason="Strong sentiment",
        ta_gate=True,
        risk_mult=0.5,
        L_mult=1.0,
    )
    packet = ResearchPacket(analysis=[approving_item], top_picks=["XYZ"], generated_at=datetime.utcnow())

    loop = LiveTradingLoop(
        config=cfg,
        datafeed=datafeed,
        analyzer=lambda snapshot, previous: _analyzer_with_signal("BUY1"),
        trade_engine=trade_engine,
        broker=broker,
        llm=None,
    )
    loop.ta_manager = _StubTAManager(packet)

    outcome = loop.run_step()

    assert outcome.action_plan["action"] == Action.BUY_INITIAL
    assert outcome.action_plan["quantity"] == pytest.approx(25.0)
    assert outcome.action_plan["ta_influence"]["applied_risk_mult"] == pytest.approx(0.5)
