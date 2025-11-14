from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from chanlun_quant.ai.context import build_synergy_payload
from chanlun_quant.ai.interface import ChanLLM, DecisionResult
from chanlun_quant.broker.interface import BrokerInterface, OrderResult
from chanlun_quant.config import Config
from chanlun_quant.datafeed.interface import DataFeed
from chanlun_quant.strategy.trade_rhythm import Action, TradeRhythmEngine
from chanlun_quant.types import Bar, PositionState, StructureState
from chanlun_quant.analysis.structure import StructureAnalyzer, build_default_analyzer

AnalyzerFunc = Callable[[Dict[str, List[Bar]], Optional[StructureState]], Tuple[StructureState, Dict[str, Any]]]
SignalResolver = Callable[[StructureState, Dict[str, Any]], str]
PriceResolver = Callable[[StructureState, Dict[str, Any], Dict[str, List[Bar]]], float]


@dataclass
class LiveStepOutcome:
    structure: StructureState
    signal: str
    action_plan: Dict[str, Any]
    decision: Optional[DecisionResult]
    order_result: Optional[OrderResult]
    extras: Dict[str, Any]


def _default_signal_resolver(structure: StructureState, extras: Dict[str, Any]) -> str:
    return str(extras.get("signal") or extras.get("primary_signal") or "HOLD").upper()


def _default_price_resolver(
    structure: StructureState,
    extras: Dict[str, Any],
    bars_by_level: Dict[str, List[Bar]],
) -> float:
    if "price" in extras and extras["price"] is not None:
        return float(extras["price"])
    for level, bars in bars_by_level.items():
        if bars:
            return float(bars[-1].close)
    return 0.0


class LiveTradingLoop:
    """Single-symbol live trading loop orchestrator."""

    def __init__(
        self,
        *,
        config: Config,
        datafeed: DataFeed,
        analyzer: Optional[AnalyzerFunc] = None,
        trade_engine: TradeRhythmEngine,
        broker: BrokerInterface,
        llm: Optional[ChanLLM] = None,
        signal_resolver: SignalResolver = _default_signal_resolver,
        price_resolver: PriceResolver = _default_price_resolver,
        levels: Optional[Sequence[str]] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.datafeed = datafeed
        self._analyzer_instance: Optional[StructureAnalyzer] = None
        if analyzer is None:
            self._analyzer_instance = build_default_analyzer(config)
            self.analyzer = self._analyzer_instance.analyze
        else:
            self.analyzer = analyzer
        self.trade_engine = trade_engine
        self.broker = broker
        self.llm = llm
        self.signal_resolver = signal_resolver
        self.price_resolver = price_resolver
        self.levels = list(levels) if levels is not None else list(config.levels)
        self.sleep_fn = sleep_fn

        self.last_structure: Optional[StructureState] = None
        self.position_manager = self.trade_engine.get_holding_manager()

    def run_step(self) -> LiveStepOutcome:
        bars_by_level = {level: self.datafeed.get_bars(level, self.config.live_lookback) for level in self.levels}
        structure, extras = self.analyzer(bars_by_level, self.last_structure)
        self.last_structure = structure

        signal = self.signal_resolver(structure, extras).upper()
        decision: Optional[DecisionResult] = None
        quantity_override: Optional[float] = None

        if self.llm and self.config.use_llm and self.config.llm_enable_structure:
            position_state = self.position_manager.get_position_state()
            payload = build_synergy_payload(structure, position_state, extras=extras, levels=self.levels)
            decision = self.llm.decide_action(payload)
            mapped_signal = self._map_decision_to_signal(decision.action, signal)
            if mapped_signal:
                signal = mapped_signal
                if decision.quantity > 0:
                    quantity_override = float(decision.quantity)

        if signal in {"", "NONE", "HOLD"}:
            action_plan = {
                "action": Action.HOLD,
                "quantity": 0.0,
                "reason": "No actionable signal",
                "stage": self.trade_engine.get_current_stage().value,
                "next_stage": self.trade_engine.get_current_stage().value,
            }
            return LiveStepOutcome(
                structure=structure,
                signal="HOLD",
                action_plan=action_plan,
                decision=decision,
                order_result=None,
                extras=extras,
            )

        price = self.price_resolver(structure, extras, bars_by_level)
        action_plan = self.trade_engine.on_signal(signal, price, self.config)
        if quantity_override is not None:
            action_plan["quantity"] = quantity_override

        order_result = self._execute_plan(action_plan, price)
        return LiveStepOutcome(
            structure=structure,
            signal=signal,
            action_plan=action_plan,
            decision=decision,
            order_result=order_result,
            extras=extras,
        )

    def run(self, *, max_steps: Optional[int] = None) -> None:
        steps = 0
        while max_steps is None or steps < max_steps:
            self.run_step()
            steps += 1
            self.sleep_fn(self.config.live_step_seconds)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _map_decision_to_signal(self, action: str, fallback: str) -> str:
        normalized = action.strip().lower()
        if normalized in {"", "none", "auto"}:
            return fallback
        if normalized == "hold":
            return "HOLD"
        if normalized == "buy":
            return "BUY1"
        if normalized in {"sell", "reduce"}:
            return "SELL1"
        if normalized == "exit":
            return "SELL_ALL"
        return fallback

    def _execute_plan(self, plan: Dict[str, Any], price: float) -> Optional[OrderResult]:
        action_value = plan.get("action", Action.HOLD)
        if isinstance(action_value, Action):
            action_enum = action_value
        else:
            try:
                action_enum = Action(str(action_value))
            except ValueError:
                action_enum = Action.HOLD

        quantity = float(plan.get("quantity", 0.0))
        symbol = self.config.symbol

        if action_enum == Action.HOLD:
            return None

        if action_enum == Action.WITHDRAW_CAPITAL:
            amount = self.position_manager.withdraw_capital()
            return OrderResult(status="withdrawn", action=action_enum.value, quantity=amount, symbol=symbol, price=None)

        if quantity <= 0:
            return None

        if action_enum in {Action.BUY_INITIAL, Action.BUY_REFILL}:
            is_initial = action_enum == Action.BUY_INITIAL
            result = self.broker.place_order(action_enum.value, quantity, symbol, price)
            self.position_manager.buy(price, quantity, is_initial_buy=is_initial)
            return result

        if action_enum in {Action.SELL_PARTIAL, Action.SELL_ALL}:
            result = self.broker.place_order(action_enum.value, quantity, symbol, price)
            self.position_manager.sell(price, quantity)
            return result

        return None
