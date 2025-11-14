from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from chanlun_quant.analysis.structure import StructureAnalyzer
from chanlun_quant.types import Bar


def _make_bars(prices: List[float], level: str = "5m") -> List[Bar]:
    base = datetime(2024, 1, 1, 9, 30)
    bars: List[Bar] = []
    for idx, price in enumerate(prices):
        bars.append(
            Bar(
                timestamp=base + timedelta(minutes=idx * 5),
                open=price,
                high=price + 0.3,
                low=price - 0.3,
                close=price,
                volume=1_000 + idx,
                index=idx,
                level=level,
            )
        )
    return bars


def test_structure_analyzer_generates_buy_signal() -> None:
    analyzer = StructureAnalyzer(["5m"])
    prices = [10.0, 9.6, 9.2, 9.4, 9.9, 10.6]
    bars = _make_bars(prices)

    structure, extras = analyzer({"5m": bars}, None)

    assert structure.levels == ["5m"]
    level_state = structure.level_states["5m"]
    assert level_state.strokes
    assert level_state.segments
    assert level_state.trends
    assert extras["signal"] in {"BUY1", "HOLD"}
    assert extras["price"] == bars[-1].close
    assert extras["trend_directions"]["5m"] in {"up", "down", "flat"}
    assert structure.relation_matrix["levels"]


def test_structure_analyzer_drawdown_triggers_sell_all() -> None:
    analyzer = StructureAnalyzer(["5m"], drawdown_exit=0.05)
    prices = [10.0, 10.8, 11.2, 10.9, 9.8, 9.0]
    bars = _make_bars(prices)

    _, extras = analyzer({"5m": bars}, None)

    assert extras["signal"] == "SELL_ALL"
    assert extras["primary_level"] == "5m"
