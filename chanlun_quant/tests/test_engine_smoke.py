from datetime import datetime, timedelta

from chanlun_quant.ai.interface import ChanLLM, LLMClient
from chanlun_quant.broker.interface import SimulatedBroker
from chanlun_quant.config import Config
from chanlun_quant.core.engine import ChanlunEngine
from chanlun_quant.types import Bar, PositionState


def _mkbars(n: int, start_idx: int = 0, level: str = "5m") -> list[Bar]:
    start_time = datetime(2024, 1, 1, 9, 30)
    bars: list[Bar] = []
    price = 100.0
    for i in range(n):
        open_ = price
        high = price + 0.5
        low = price - 0.5
        close = price + 0.2
        bars.append(
            Bar(
                timestamp=start_time + timedelta(minutes=i),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=1000,
                index=start_idx + i,
                level=level,
            )
        )
        price = close
    return bars


def test_analyze_one_and_multi_and_decide_execute_smoke():
    cfg = Config()
    engine = ChanlunEngine(cfg=cfg, llm=ChanLLM(client=LLMClient("mock")), broker=SimulatedBroker())

    bars_5m = _mkbars(60, start_idx=0, level="5m")
    single = engine.analyze_one_level(bars_5m, "5m")
    assert {"level", "bars", "fractals", "strokes", "segments", "centrals", "macd", "signals"}.issubset(single.keys())

    level_bars = {
        "5m": bars_5m,
        "30m": _mkbars(60, start_idx=1000, level="30m"),
        "1d": _mkbars(60, start_idx=2000, level="1d"),
    }
    multi = engine.analyze_multi_level(level_bars)
    assert {"levels", "structure", "fusion"}.issubset(multi.keys())
    assert "resonance" in multi["fusion"]

    position = PositionState(
        quantity=0,
        avg_cost=0.0,
        realized_profit=0.0,
        remaining_capital=100_000.0,
        stage="INITIAL",
    )
    result = engine.decide_and_execute(level_bars, position)
    assert {"analysis", "ai", "execution"}.issubset(result.keys())
    assert result["execution"]["status"] in {"skipped", "filled"}
