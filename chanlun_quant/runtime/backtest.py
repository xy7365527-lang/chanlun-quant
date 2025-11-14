from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from chanlun_quant.ai.interface import ChanLLM
from chanlun_quant.broker.interface import BrokerInterface, SimulatedBroker
from chanlun_quant.config import Config
from chanlun_quant.datafeed.interface import DataFeed
from chanlun_quant.runtime.live_loop import AnalyzerFunc, LiveStepOutcome, LiveTradingLoop
from chanlun_quant.strategy.trade_rhythm import TradeRhythmEngine
from chanlun_quant.types import Bar, StructureState


class HistoricalDataFeed(DataFeed):
    """Incremental bar access for backtesting."""

    def __init__(self, bars_by_level: Dict[str, List[Bar]]) -> None:
        if not bars_by_level:
            raise ValueError("bars_by_level cannot be empty")
        self._bars = {level: list(bars) for level, bars in bars_by_level.items()}
        self._indices = {level: -1 for level in bars_by_level}

    def advance(self) -> bool:  # type: ignore[override]
        progressed = False
        for level, bars in self._bars.items():
            idx = self._indices[level]
            if idx + 1 < len(bars):
                self._indices[level] = idx + 1
                progressed = True
        return progressed

    def get_bars(self, level: str, lookback: int = 300) -> List[Bar]:  # type: ignore[override]
        idx = self._indices.get(level, -1)
        if idx < 0:
            return []
        bars = self._bars[level]
        start = max(0, idx - lookback + 1)
        return bars[start : idx + 1]

    @property
    def exhausted(self) -> bool:
        return all(self._indices[level] >= len(self._bars[level]) - 1 for level in self._bars)


@dataclass
class BacktestResult:
    outcomes: List[LiveStepOutcome]
    final_structure: Optional[StructureState]

    @property
    def trades(self) -> List[LiveStepOutcome]:
        return [out for out in self.outcomes if out.order_result is not None]


class BacktestRunner:
    """Replay historical bars through the live trading loop."""

    def __init__(
        self,
        *,
        config: Config,
        bars_by_level: Dict[str, List[Bar]],
        analyzer: Optional[AnalyzerFunc] = None,
        trade_engine: Optional[TradeRhythmEngine] = None,
        broker: Optional[BrokerInterface] = None,
        llm: Optional[ChanLLM] = None,
        levels: Optional[Sequence[str]] = None,
    ) -> None:
        self.datafeed = HistoricalDataFeed(bars_by_level)
        trade_engine = trade_engine or TradeRhythmEngine()
        self.loop = LiveTradingLoop(
            config=config,
            datafeed=self.datafeed,
            analyzer=analyzer,
            trade_engine=trade_engine,
            broker=broker or SimulatedBroker(),
            llm=llm,
            levels=levels,
            sleep_fn=lambda _: None,
        )
        self.outcomes: List[LiveStepOutcome] = []

    def run(self) -> BacktestResult:
        while self.datafeed.advance():
            outcome = self.loop.run_step()
            self.outcomes.append(outcome)
        return BacktestResult(outcomes=self.outcomes, final_structure=self.loop.last_structure)
