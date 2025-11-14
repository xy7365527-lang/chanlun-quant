from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

from chanlun_quant.broker.interface import SimulatedBroker
from chanlun_quant.config import Config
from chanlun_quant.runtime.backtest import BacktestRunner
from chanlun_quant.strategy.trade_rhythm import TradeRhythmEngine
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


def _make_bars(level: str, length: int, base: datetime, step: timedelta) -> List[Bar]:
    bars: List[Bar] = []
    for idx in range(length):
        ts = base + step * idx
        price = 10.0 + idx * 0.1
        bars.append(
            Bar(
                timestamp=ts,
                open=price,
                high=price + 0.5,
                low=price - 0.5,
                close=price + 0.2,
                volume=1_000 + idx,
                index=idx,
                level=level,
            )
        )
    return bars


def _build_structure(level: str) -> StructureState:
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
    level_state = StructureLevelState(
        level=level,
        strokes={stroke.id: stroke},
        segments={segment.id: segment},
        trends={trend.id: trend},
        active_trend_id=trend.id,
        signals=[signal],
    )
    mapping = MultiLevelMapping(higher_level="30m", lower_level=level)
    return StructureState(
        levels=[level],
        level_states={level: level_state},
        multilevel_mappings=[mapping],
        relation_matrix={"summary": "mock"},
    )


def test_backtest_runner_executes_all_steps() -> None:
    level = "5m"
    bars_by_level = {level: _make_bars(level, 3, datetime(2024, 1, 1), timedelta(minutes=1))}
    cfg = Config(levels=(level,), initial_buy_quantity=50)
    broker = SimulatedBroker()
    engine = TradeRhythmEngine()

    def analyzer(bars: Dict[str, List[Bar]], previous_structure: StructureState | None):
        structure = _build_structure(level)
        step = len(next(iter(bars.values())))
        extras = {"signal": "BUY1", "price": 10.5}
        if step >= 2:
            extras["signal"] = "SELL1"
        if step >= 3:
            extras["signal"] = "SELL_ALL"
        return structure, extras

    runner = BacktestRunner(
        config=cfg,
        bars_by_level=bars_by_level,
        analyzer=analyzer,
        trade_engine=engine,
        broker=broker,
    )
    result = runner.run()

    assert len(result.outcomes) == 3
    assert result.trades
    final_state = engine.get_holding_manager().state
    assert final_state.stage in {"HOLDING", "PARTIAL_SOLD", "PROFIT_HOLD", "INITIAL"}
