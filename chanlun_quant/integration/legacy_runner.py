from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from chanlun_quant.broker.interface import OrderResult, SimulatedBroker
from chanlun_quant.config import Config
from chanlun_quant.integration.datafeed import load_legacy_bars
from chanlun_quant.integration.legacy_market import LegacyMarketDataBridge
from chanlun_quant.runtime.backtest import BacktestResult, BacktestRunner
from chanlun_quant.strategy import Action, LegacyStrategyAdapter, TradeRhythmEngine
from chanlun_quant.types import Bar, StructureState


@dataclass
class MigrationSummary:
    result: BacktestResult
    summary: Dict[str, Any]
    engine: TradeRhythmEngine


class AdapterSimulatedBroker(SimulatedBroker):
    """Simulated broker that keeps the legacy adapter in sync with executed trades."""

    def __init__(self, adapter: LegacyStrategyAdapter, *, initial_cash: float) -> None:
        super().__init__(initial_cash=initial_cash)
        self.adapter = adapter

    def place_order(self, action: str, quantity: float, symbol: str, price: float | None = None) -> OrderResult:
        result = super().place_order(action, quantity, symbol, price)
        try:
            action_enum = Action(action)
        except ValueError:
            action_enum = Action.HOLD

        if action_enum in {Action.BUY_INITIAL, Action.BUY_REFILL, Action.SELL_PARTIAL, Action.SELL_ALL}:
            effective_price = result.price if result.price is not None else price or 0.0
            self.adapter.register_fill(action_enum, result.quantity, effective_price)
        return result


def _filter_bars_to_timestamp(bars: Sequence[Bar], cutoff: Optional[Any]) -> List[Bar]:
    if cutoff is None:
        return list(bars)
    return [bar for bar in bars if bar.timestamp <= cutoff]


def ensure_index_freqs(index_freqs_arg: Optional[Sequence[str]], primary_freqs: Sequence[str]) -> Sequence[str]:
    if index_freqs_arg:
        return tuple(index_freqs_arg)
    return tuple(primary_freqs)


def build_legacy_analyzer(
    market: str,
    symbol: str,
    index_symbol: Optional[str],
    adapter: LegacyStrategyAdapter,
    market_bridge: LegacyMarketDataBridge,
    index_bars: Mapping[str, List[Bar]],
    frequencys: Sequence[str],
) -> Any:
    primary_freq = frequencys[-1]

    def analyzer(bars_by_level: Dict[str, List[Bar]], previous: Optional[StructureState]) -> Tuple[StructureState, Dict[str, Any]]:
        if not bars_by_level.get(primary_freq):
            return StructureState(levels=list(frequencys)), {"signal": "HOLD"}

        last_timestamp = bars_by_level[primary_freq][-1].timestamp

        market_bridge.set_symbol_bars(symbol, bars_by_level)

        if index_symbol:
            index_payload: Dict[str, List[Bar]] = {}
            for level, bars in index_bars.items():
                index_payload[level] = _filter_bars_to_timestamp(bars, last_timestamp)
            market_bridge.set_symbol_bars(index_symbol, index_payload, frequencys=frequencys)

        signal = adapter.step(market_bridge)
        extras: Dict[str, Any] = {
            "source": "legacy_strategy",
            "symbol": symbol,
            "signal": "HOLD" if signal is None else signal.signal,
        }
        if signal:
            extras.update(
                {
                    "price": signal.price,
                    "legacy_reason": signal.reason,
                    "legacy_operation": signal.operation.mmd,
                    "legacy_pos_rate": signal.pos_rate,
                }
            )

        structure = StructureState(levels=list(frequencys))
        return structure, extras

    return analyzer


def summarize_backtest(result: BacktestResult, engine: TradeRhythmEngine) -> Dict[str, Any]:
    state = engine.get_holding_manager().state
    summary = {
        "steps": len(result.outcomes),
        "trades": len(result.trades),
        "final_stage": engine.get_current_stage().value,
        "final_quantity": state.quantity,
        "avg_cost": state.avg_cost,
        "realized_profit": state.realized_profit,
        "withdrawn_capital": state.withdrawn_capital,
    }
    return summary


def load_strategy(path: str, strategy_kwargs: Optional[Dict[str, Any]] = None) -> Any:
    if ":" not in path:
        raise ValueError("strategy path must be in format 'module:ClassName'")
    module_name, class_name = path.split(":", 1)
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    kwargs = strategy_kwargs or {}
    return cls(**kwargs)


def run_legacy_strategy(
    *,
    strategy,
    symbol: str,
    market: str,
    freqs: Sequence[str],
    index_symbol: Optional[str] = None,
    index_freqs: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
    order: str = "asc",
    config_kwargs: Optional[Dict[str, Any]] = None,
    trade_engine_kwargs: Optional[Dict[str, Any]] = None,
) -> MigrationSummary:
    freqs = tuple(freqs)
    if not freqs:
        raise ValueError("freqs cannot be empty")

    bars_by_level = load_legacy_bars(
        symbol=symbol,
        freqs=freqs,
        market=market,
        limit=limit,
        order=order,
    )

    index_bars_by_level: Dict[str, List[Bar]] = {}
    if index_symbol:
        index_bars_by_level = load_legacy_bars(
            symbol=index_symbol,
            freqs=ensure_index_freqs(index_freqs, freqs),
            market=market,
            limit=limit,
            order=order,
        )

    adapter = LegacyStrategyAdapter(symbol=symbol, strategy=strategy)
    bridge = LegacyMarketDataBridge(market, symbol, freqs)
    analyzer = build_legacy_analyzer(
        market=market,
        symbol=symbol,
        index_symbol=index_symbol,
        adapter=adapter,
        market_bridge=bridge,
        index_bars=index_bars_by_level,
        frequencys=freqs,
    )

    config_kwargs = config_kwargs or {}
    default_cfg = {
        "symbol": symbol,
        "levels": tuple(freqs),
        "initial_capital": 100_000.0,
        "initial_buy_quantity": 0.0,
        "partial_sell_ratio": 0.5,
        "profit_sell_ratio": 0.3,
        "profit_buy_quantity": 0.0,
        "use_llm": False,
    }
    default_cfg.update(config_kwargs)
    cfg = Config(**default_cfg)

    trade_engine_kwargs = trade_engine_kwargs or {}
    engine = TradeRhythmEngine(
        initial_capital=cfg.initial_capital,
        initial_quantity=trade_engine_kwargs.get("initial_quantity", cfg.initial_buy_quantity),
    )
    broker = AdapterSimulatedBroker(adapter, initial_cash=cfg.initial_capital)

    runner = BacktestRunner(
        config=cfg,
        bars_by_level=bars_by_level,
        analyzer=analyzer,
        trade_engine=engine,
        broker=broker,
        llm=None,
        levels=freqs,
    )
    result = runner.run()
    summary = summarize_backtest(result, engine)

    return MigrationSummary(result=result, summary=summary, engine=engine)


def export_summary(summary: Mapping[str, Any], path: Optional[Path]) -> None:
    if path is None:
        return
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

