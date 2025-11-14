from __future__ import annotations

import logging
import math
import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from chanlun_quant.ai.context import build_position_payload, build_structure_payload, build_synergy_payload
from chanlun_quant.ai.interface import ChanLLM, DecisionResult, PlanDecisionResult, StageMemoryResult
from chanlun_quant.ai.performance import PerformanceTracker
from chanlun_quant.ai.trading_agents import ResearchItem, ResearchPacket, TradingAgentsManager
from chanlun_quant.broker.interface import BrokerInterface, OrderResult
from chanlun_quant.config import Config
from chanlun_quant.datafeed.interface import DataFeed
from chanlun_quant.strategy.trade_rhythm import Action, TradeRhythmEngine
from chanlun_quant.types import Bar, PositionState, StructureState
from chanlun_quant.analysis.structure import StructureAnalyzer, build_default_analyzer
from chanlun_quant.risk import combine_leverage, estimate_liq_price

LOGGER = logging.getLogger(__name__)

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
    plan: Optional[PlanDecisionResult] = None
    executions: Optional[List[Dict[str, Any]]] = None
    stage_memory: Optional[StageMemoryResult] = None
    notes: Optional[str] = None
    ta_packet: Optional[Dict[str, Any]] = None
    performance: Optional[Dict[str, Any]] = None


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


def _coerce_action(value: Any) -> Action:
    if isinstance(value, Action):
        return value
    try:
        return Action(str(value))
    except ValueError:
        return Action.HOLD


def _apply_ta_constraints_to_plan(
    *,
    plan: Dict[str, Any],
    ta_item: Optional[ResearchItem],
    config: Config,
    position_state: PositionState,
    price: float,
    structure: StructureState,
    extras: Dict[str, Any],
    bars_by_level: Dict[str, List[Bar]],
    signal: str,
) -> Dict[str, Any]:
    del price, structure, extras, bars_by_level  # currently unused but reserved for future heuristics

    adjusted_plan = dict(plan)
    adjusted_plan.setdefault("warnings", [])
    adjusted_plan.setdefault("ta_notes", [])

    action = _coerce_action(adjusted_plan.get("action", Action.HOLD))
    adjusted_plan["action"] = action

    normalized_signal = (signal or "").upper()
    stage_text = str(getattr(position_state, "cost_stage", position_state.stage) or position_state.stage or "INITIAL").upper()

    if ta_item is None:
        influence = {
            "present": False,
            "gate_pass": True,
            "recommendation": None,
            "risk_mult_requested": 1.0,
            "L_mult_requested": 1.0,
            "blocked": False,
            "llm_signal": normalized_signal,
            "stage": stage_text,
        }
        if config.ta_enabled and stage_text == "INITIAL" and action in {Action.BUY_INITIAL, Action.BUY_REFILL}:
            adjusted_plan["action"] = Action.HOLD
            adjusted_plan["quantity"] = 0.0
            adjusted_plan["reason"] = "TradingAgents research unavailable, skip initial entry"
            adjusted_plan["warnings"].append("ta_missing_initial")
            allowed = adjusted_plan.get("allowed_actions")
            if isinstance(allowed, list) and "HOLD" not in allowed:
                allowed.append("HOLD")
            influence["blocked"] = True
            influence["blocked_action"] = action.value
        if normalized_signal == "SELL_ALL" and action != Action.SELL_ALL:
            qty = float(position_state.quantity)
            if qty > 0:
                adjusted_plan["action"] = Action.SELL_ALL
                adjusted_plan["quantity"] = qty
                adjusted_plan["reason"] = "LLM override: SELL_ALL"
                adjusted_plan["next_stage"] = "EXIT"
                allowed = adjusted_plan.get("allowed_actions")
                if isinstance(allowed, list) and "SELL_ALL" not in allowed:
                    allowed.append("SELL_ALL")
                influence["llm_override"] = "SELL_ALL"
        adjusted_plan["ta_influence"] = influence
        return adjusted_plan

    ta_dict = ta_item.to_dict()
    gate_reasons: List[str] = []
    if ta_item.kill_switch:
        gate_reasons.append("kill_switch")
    if not ta_item.ta_gate:
        gate_reasons.append("ta_gate_false")
    if ta_item.score < config.ta_score_threshold:
        gate_reasons.append("score_below_threshold")

    gate_pass = not gate_reasons

    influence: Dict[str, Any] = {
        "present": True,
        "gate_pass": gate_pass,
        "gate_reasons": gate_reasons,
        "ta_gate": ta_item.ta_gate,
        "kill_switch": ta_item.kill_switch,
        "score": ta_item.score,
        "score_threshold": config.ta_score_threshold,
        "recommendation": ta_item.recommendation,
        "risk_mult_requested": ta_item.risk_mult,
        "L_mult_requested": ta_item.L_mult,
        "risk_flags": list(getattr(ta_item, "risk_flags", [])),
        "risk_notes": list(getattr(ta_item, "risk_notes", [])),
        "stage": stage_text,
        "ta_item": ta_dict,
        "llm_signal": normalized_signal,
    }

    if ta_item.reason:
        adjusted_plan["ta_notes"].append(ta_item.reason)
    influence["blocked"] = False

    hard_block_actions = {Action.BUY_INITIAL, Action.BUY_REFILL}
    if not gate_pass:
        LOGGER.info(
            "TradingAgents gate not passed (symbol=%s, stage=%s, reasons=%s)",
            config.symbol,
            stage_text,
            ",".join(gate_reasons) or "unknown",
        )
        if action in hard_block_actions and getattr(config, "ta_skip_on_fail", True):
            influence["blocked"] = True
            influence["blocked_action"] = action.value
            adjusted_plan["action"] = Action.HOLD
            adjusted_plan["quantity"] = 0.0
            adjusted_plan["reason"] = (
                f"Blocked by TradingAgents ({'; '.join(gate_reasons) or ta_item.recommendation})"
            )
            adjusted_plan["warnings"].append("ta_blocked")
            adjusted_plan["ta_influence"] = influence
            return adjusted_plan
        adjusted_plan["warnings"].append("ta_soft_warning")

    risk_mult = max(0.0, ta_item.risk_mult)
    applied_risk_mult = 1.0
    if action in hard_block_actions:
        base_qty = float(adjusted_plan.get("quantity", 0.0) or 0.0)
        if base_qty > 0 and risk_mult != 1.0:
            adjusted_qty = base_qty * risk_mult
            applied_risk_mult = risk_mult
            adjusted_plan["quantity"] = adjusted_qty
            adjusted_plan["warnings"].append("ta_risk_adjusted_quantity")
            if adjusted_qty <= 0:
                influence["blocked"] = True
                influence["blocked_action"] = action.value
                adjusted_plan["action"] = Action.HOLD
                adjusted_plan["quantity"] = 0.0
                adjusted_plan["reason"] = "TradingAgents risk multiplier removed position"
                adjusted_plan["warnings"].append("ta_quantity_zero")
                adjusted_plan["ta_influence"] = influence
                return adjusted_plan
        elif base_qty <= 0 and risk_mult < 1.0:
            applied_risk_mult = risk_mult
    influence["applied_risk_mult"] = applied_risk_mult

    leverage_value = adjusted_plan.get("leverage")
    applied_leverage_mult = 1.0
    if (
        config.use_leverage
        and leverage_value is not None
        and isinstance(leverage_value, (int, float))
        and leverage_value > 0
    ):
        base_leverage = float(leverage_value)
        requested_mult = max(0.0, ta_item.L_mult)
        leverage_adjusted = base_leverage * requested_mult
        leverage_cap = min(config.exch_max_leverage, config.max_leverage_config)
        leverage_adjusted = max(1.0, min(leverage_adjusted, leverage_cap))
        influence["leverage_before"] = base_leverage
        influence["leverage_after"] = leverage_adjusted
        adjusted_plan["leverage"] = leverage_adjusted
        applied_leverage_mult = leverage_adjusted / base_leverage if base_leverage > 0 else requested_mult
        influence["leverage_clamped"] = leverage_adjusted != base_leverage * requested_mult
    influence["applied_L_mult"] = applied_leverage_mult

    tighten_stop = bool(getattr(ta_item, "risk_flags", []) or getattr(ta_item, "risk_notes", []))
    influence["tighten_stop"] = tighten_stop
    if tighten_stop:
        adjusted_plan["warnings"].append("ta_risk_flags_present")

    if normalized_signal == "SELL_ALL" and action != Action.SELL_ALL:
        qty = float(position_state.quantity)
        if qty > 0:
            adjusted_plan["action"] = Action.SELL_ALL
            adjusted_plan["quantity"] = qty
            adjusted_plan["reason"] = "LLM override: SELL_ALL"
            adjusted_plan["next_stage"] = "EXIT"
            allowed = adjusted_plan.get("allowed_actions")
            if isinstance(allowed, list) and "SELL_ALL" not in allowed:
                allowed.append("SELL_ALL")
            influence["llm_override"] = "SELL_ALL"

    adjusted_plan["ta_influence"] = influence
    return adjusted_plan


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
        self._using_prompt_pack = bool(self.llm and self.config.use_llm and self.config.llm_use_prompt_pack)
        self._start_time = time.time()
        self._step_counter = 0
        self.ta_manager: Optional[TradingAgentsManager] = (
            TradingAgentsManager(config) if getattr(config, "ta_enabled", False) else None
        )
        self.performance_tracker = PerformanceTracker()

    def run_step(self) -> LiveStepOutcome:
        bars_by_level = {level: self.datafeed.get_bars(level, self.config.live_lookback) for level in self.levels}
        structure, extras = self.analyzer(bars_by_level, self.last_structure)
        self.last_structure = structure

        position_state = self.position_manager.get_position_state()
        signal = self.signal_resolver(structure, extras).upper()
        price = self.price_resolver(structure, extras, bars_by_level)
        rhythm_plan = self.trade_engine.on_signal(signal, price, self.config)

        ta_packet_obj = None
        ta_packet_dict: Optional[Dict[str, Any]] = None
        ta_items_map: Dict[str, ResearchItem] = {}
        ta_primary: Optional[ResearchItem] = None
        performance_before = self.performance_tracker.summary()
        if self.ta_manager is not None and self.ta_manager.enabled:
            ta_packet_obj, ta_packet_dict, ta_items_map = self._get_trading_research(
                symbol=self.config.symbol,
                signal=signal,
                structure=structure,
                extras=extras,
                position_state=position_state,
                price=price,
            )
            ta_primary = ta_items_map.get(self.config.symbol.upper())

        if self._using_prompt_pack and self.llm:
            outcome = self._run_prompt_pack_step(
                bars_by_level=bars_by_level,
                structure=structure,
                extras=extras,
                signal=signal,
                price=price,
                rhythm_plan=rhythm_plan,
                position_state=position_state,
                ta_packet=ta_packet_dict,
                ta_items_map=ta_items_map,
                performance_summary=performance_before,
            )
            executions = outcome.executions or []
            primary_action = Action.HOLD
            for exec_result in executions:
                decision = exec_result.get("decision") if isinstance(exec_result, dict) else None
                if isinstance(decision, dict):
                    mapped_action = decision.get("mapped_action") or decision.get("action_override") or decision.get("action")
                    if mapped_action:
                        try:
                            primary_action = Action(str(mapped_action))
                        except ValueError:
                            primary_action = Action.HOLD
                        break
            executed_flag = any(bool(exec_result.get("executed")) for exec_result in executions)
            perf_summary = self.performance_tracker.update(
                primary_action,
                executed_flag,
                position_state,
                price,
            )
            outcome.performance = perf_summary
            self._step_counter += 1
            return outcome

        decision: Optional[DecisionResult] = None
        quantity_override: Optional[float] = None

        if self.llm and self.config.use_llm and self.config.llm_enable_structure:
            payload = build_synergy_payload(
                structure,
                position_state,
                extras=extras,
                levels=self.levels,
                performance=performance_before,
                ta_packet=ta_packet_dict,
                ta_focus=ta_primary.to_dict() if ta_primary else None,
            )
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
            self.trade_engine.cost_stage = self.position_manager.get_position_state().cost_stage
            outcome = LiveStepOutcome(
                structure=structure,
                signal="HOLD",
                action_plan=action_plan,
                decision=decision,
                order_result=None,
                extras=extras,
                ta_packet=ta_packet_dict,
            )
            executed_flag = False
            outcome.performance = self.performance_tracker.update(
                Action.HOLD,
                executed_flag,
                position_state,
                price,
            )
            self._step_counter += 1
            return outcome

        action_plan = dict(rhythm_plan)
        if quantity_override is not None:
            action_plan["quantity"] = quantity_override

        action_plan = _apply_ta_constraints_to_plan(
            plan=action_plan,
            ta_item=ta_primary,
            config=self.config,
            position_state=position_state,
            price=price,
            structure=structure,
            extras=extras,
            bars_by_level=bars_by_level,
            signal=signal,
        )

        order_result = self._execute_plan(action_plan, price)
        self.trade_engine.cost_stage = self.position_manager.get_position_state().cost_stage
        outcome = LiveStepOutcome(
            structure=structure,
            signal=signal,
            action_plan=action_plan,
            decision=decision,
            order_result=order_result,
            extras=extras,
            ta_packet=ta_packet_dict,
        )
        executed_flag = bool(order_result)
        outcome.performance = self.performance_tracker.update(
            _coerce_action(action_plan.get("action", Action.HOLD)),
            executed_flag,
            position_state,
            price,
        )
        self._step_counter += 1
        return outcome

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
        leverage = plan.get("leverage")
        margin_mode = plan.get("margin_mode")

        if action_enum == Action.HOLD:
            return None

        if action_enum == Action.WITHDRAW_CAPITAL:
            amount = self.position_manager.withdraw_capital()
            return OrderResult(status="withdrawn", action=action_enum.value, quantity=amount, symbol=symbol, price=None)

        if quantity <= 0:
            return None

        if action_enum in {Action.BUY_INITIAL, Action.BUY_REFILL}:
            is_initial = action_enum == Action.BUY_INITIAL
            result = self.broker.place_order(action_enum.value, quantity, symbol, price, leverage=leverage, margin_mode=margin_mode)
            self.position_manager.buy(price, quantity, is_initial_buy=is_initial)
            return result

        if action_enum in {Action.SELL_PARTIAL, Action.SELL_ALL}:
            result = self.broker.place_order(action_enum.value, quantity, symbol, price, leverage=leverage, margin_mode=margin_mode)
            self.position_manager.sell(price, quantity)
            return result

        return None

    # ------------------------------------------------------------------
    # Prompt-pack helpers
    # ------------------------------------------------------------------
    def _run_prompt_pack_step(
        self,
        bars_by_level: Dict[str, List[Bar]],
        structure: StructureState,
        extras: Dict[str, Any],
        signal: str,
        price: float,
        rhythm_plan: Dict[str, Any],
        position_state: PositionState,
        ta_packet: Optional[Dict[str, Any]],
        ta_items_map: Dict[str, ResearchItem],
        performance_summary: Optional[Dict[str, Any]],
    ) -> LiveStepOutcome:
        assert self.llm is not None  # for type checking

        ctx = self._build_prompt_contexts(
            structure=structure,
            extras=extras,
            position_state=position_state,
            signal=signal,
            price=price,
            rhythm_plan=rhythm_plan,
            ta_packet=ta_packet,
            performance_summary=performance_summary,
        )
        minutes_elapsed = int(max(time.time() - self._start_time, 0) // 60)

        plan_result = self.llm.plan_decision(
            minutes_elapsed=minutes_elapsed,
            structure_json=ctx["structure_json"],
            momentum_json=ctx["momentum_json"],
            fusion_json=ctx["fusion_json"],
            account_json=ctx["account_json"],
            constraints_text=ctx["constraints_text"],
            ta_json=ctx["ta_json"],
            performance_json=ctx["performance_json"],
        )

        allowed_actions = self._parse_allowed_actions(rhythm_plan.get("allowed_actions"))
        executions: List[Dict[str, Any]] = []
        sanitized_decisions: List[Dict[str, Any]] = []
        if plan_result.decisions:
            for decision in plan_result.decisions:
                decision_symbol = str(decision.get("symbol", self.config.symbol) or self.config.symbol)
                ta_item = ta_items_map.get(decision_symbol.upper())
                exec_result = self._execute_prompt_decision(
                    decision=decision,
                    price=price,
                    allowed_actions=allowed_actions,
                    position_state=position_state,
                    structure=structure,
                    extras=extras,
                    bars_by_level=bars_by_level,
                    ta_item=ta_item,
                )
                executions.append(exec_result)
                sanitized_decisions.append(exec_result.get("decision", decision))

        memory_result: Optional[StageMemoryResult] = None
        try:
            updated_snapshot = build_position_payload(position_state)
            memory_payload = {
                "structure": ctx["structure_payload"],
                "position": updated_snapshot,
                "decisions": sanitized_decisions,
                "executions": executions,
                "notes": plan_result.notes,
                "plan_raw": plan_result.raw,
                "trade_plan": ctx["trade_plan"],
                "ta": ta_packet,
                "ta_summary": ctx.get("ta_summary"),
                "performance": ctx.get("performance_summary"),
            }
            memory_context = json.dumps(memory_payload, ensure_ascii=False, indent=2)
            memory_result = self.llm.stage_memory(memory_context=memory_context)
            if memory_result.stage_after:
                position_state.cost_stage = memory_result.stage_after
                self.trade_engine.cost_stage = memory_result.stage_after
        except Exception:
            memory_result = None

        outcome = LiveStepOutcome(
            structure=structure,
            signal=signal,
            action_plan={"prompt_decisions": sanitized_decisions, "notes": plan_result.notes},
            decision=None,
            order_result=None,
            extras=extras,
            plan=plan_result,
            executions=executions,
            stage_memory=memory_result,
            notes=plan_result.notes,
            ta_packet=ta_packet,
        )
        return outcome

    def _build_prompt_contexts(
        self,
        structure: StructureState,
        extras: Dict[str, Any],
        position_state: PositionState,
        signal: str,
        price: float,
        rhythm_plan: Dict[str, Any],
        ta_packet: Optional[Dict[str, Any]],
        performance_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        structure_payload = build_structure_payload(structure, levels=self.levels)
        structure_section = {
            "primary_signal": signal,
            "primary_level": extras.get("primary_level"),
            "levels": structure_payload.get("levels"),
            "level_details": structure_payload.get("level_details"),
            "signals": extras.get("level_signals", {}),
        }
        structure_json = json.dumps(structure_section, ensure_ascii=False, indent=2)

        momentum_section = {
            "trend_directions": extras.get("trend_directions", {}),
            "relation_summary": extras.get("relation_summary"),
            "level_signals": extras.get("level_signals", {}),
            "last_price": price,
        }
        momentum_json = json.dumps(momentum_section, ensure_ascii=False, indent=2)

        fusion_json = json.dumps(structure.relation_matrix or {}, ensure_ascii=False, indent=2)

        position_snapshot = build_position_payload(position_state)
        account_section = {
            "symbol": self.config.symbol,
            "stage": position_state.stage,
            "cost_stage": getattr(position_state, "cost_stage", "INITIAL"),
            "position": position_snapshot,
            "cash": {
                "remaining_capital": position_state.remaining_capital,
                "withdrawn_capital": position_state.withdrawn_capital,
            },
            "fee_rate_bp": 0.0,
            "slippage_bp": 0.0,
            "leverage_limits": {
                "exch_max": self.config.exch_max_leverage,
                "cfg_max": self.config.max_leverage_config,
                "step": self.config.leverage_step,
                "mm": self.config.exch_maint_margin,
                "liq_buffer": self.config.liq_buffer_ratio,
                "prefer_isolated": self.config.prefer_isolated_margin,
            },
        }
        account_json = json.dumps(account_section, ensure_ascii=False, indent=2)

        trade_plan_serialized = self._serialize_trade_plan(rhythm_plan)

        constraints_lines = [
            "* 风控红线：禁止无计划加仓，SELL 信号优先级 > BUY 信号。",
            f"* partial_sell_ratio={self.config.partial_sell_ratio}, profit_sell_ratio={self.config.profit_sell_ratio}，profit_buy_quantity={self.config.profit_buy_quantity}。",
            "* 成本推进顺序：COST_DOWN → ZERO_COST → NEG_COST → WITHDRAW，未覆盖成本不得提现。",
            "* BUY 仅限结构 BUY1/BUY2/BUY3，SELL 在 SELL1/SELL2/SELL3 或背驰离开中枢时执行。",
            f"* 允许动作集合：{', '.join(trade_plan_serialized.get('allowed_actions', []))}，请严格遵守。",
            f"* 杠杆约束：exch_max={self.config.exch_max_leverage}, cfg_max={self.config.max_leverage_config}, step={self.config.leverage_step}, mm={self.config.exch_maint_margin}, buffer={self.config.liq_buffer_ratio}。",
            "* 单笔指令需输出: action, quantity/position_ratio, leverage, stop_loss, take_profit, confidence, reasoning。",
            "* 若 TradingAgents 提示 kill_switch 或 ta_gate=false，必须返回 SKIP/HOLD 并说明原因。",
        ]
        constraints_text = "\n".join(constraints_lines)

        ta_summary: Dict[str, Any]
        if ta_packet:
            symbol_upper = self.config.symbol.upper()
            focus = None
            for item in ta_packet.get("analysis", []):
                sym = str(item.get("symbol", "")).upper()
                if sym == symbol_upper:
                    focus = item
                    break
            ta_summary = {
                "present": True,
                "symbol": self.config.symbol,
                "focus": focus,
                "packet": ta_packet,
            }
        else:
            ta_summary = {
                "present": False,
                "symbol": self.config.symbol,
                "note": "无 TradingAgents 快照，默认按结构策略执行",
            }
        ta_json = json.dumps(ta_summary, ensure_ascii=False, indent=2)

        performance_summary = performance_summary or self.performance_tracker.summary()
        performance_json = json.dumps(performance_summary, ensure_ascii=False, indent=2)

        return {
            "structure_json": structure_json,
            "momentum_json": momentum_json,
            "fusion_json": fusion_json,
            "account_json": account_json,
            "constraints_text": constraints_text,
            "structure_payload": structure_payload,
            "trade_plan": trade_plan_serialized,
            "ta_packet": ta_packet,
            "ta_json": ta_json,
            "ta_summary": ta_summary,
            "performance_json": performance_json,
            "performance_summary": performance_summary,
        }

    def _execute_prompt_decision(
        self,
        decision: Dict[str, Any],
        price: float,
        allowed_actions: Set[Action],
        position_state: PositionState,
        *,
        structure: StructureState,
        extras: Dict[str, Any],
        bars_by_level: Dict[str, List[Bar]],
        ta_item: Optional[ResearchItem] = None,
    ) -> Dict[str, Any]:
        action_str = str(decision.get("action", "HOLD"))
        mapped_action = self._map_prompt_action(action_str)
        result: Dict[str, Any] = {
            "action": action_str,
            "mapped_action": mapped_action.value if mapped_action else None,
            "quantity": decision.get("quantity", 0.0),
            "executed": False,
            "errors": [],
            "warnings": [],
        }

        decision_symbol = str(decision.get("symbol", self.config.symbol) or self.config.symbol)
        sanitized_decision = dict(decision)
        sanitized_decision["symbol"] = decision_symbol
        sanitized_decision["mapped_action"] = result["mapped_action"]
        sanitized_decision["initial_quantity"] = result["quantity"]

        research_item = ta_item
        if research_item is not None:
            sanitized_decision["ta_analysis"] = research_item.to_dict()
            gate_pass = research_item.ta_gate and research_item.score >= self.config.ta_score_threshold
            sanitized_decision["ta_gate"] = research_item.ta_gate
            sanitized_decision["ta_score"] = research_item.score
            sanitized_decision["ta_gate_decision"] = gate_pass
            if research_item.risk_flags:
                sanitized_decision["ta_risk_flags"] = list(research_item.risk_flags)
            if not gate_pass:
                message = "ta_gate_blocked" if not research_item.ta_gate else "ta_score_below_threshold"
                if self.config.ta_gate_mode.lower() == "hard":
                    result["errors"].append(message)
                    sanitized_decision["validation_errors"] = result["errors"]
                    sanitized_decision["warnings"] = result["warnings"]
                    sanitized_decision["action_override"] = "SKIP"
                    result["decision"] = sanitized_decision
                    result["leverage_eval"] = {
                        "L_proposed": float(decision.get("leverage", 1.0) or 1.0),
                        "L_final": 0.0,
                        "L_suggest": 0.0,
                        "L0_cap": 0.0,
                        "liq_price_est": 0.0,
                        "atr_norm": 0.0,
                        "fusion_score": 0.0,
                    }
                    return result
                result["warnings"].append(message)
            risk_mult = max(0.0, research_item.risk_mult)
            L_mult = max(0.0, research_item.L_mult)
            sanitized_decision["ta_risk_mult"] = risk_mult
            sanitized_decision["ta_leverage_mult"] = L_mult
        else:
            risk_mult = 1.0
            L_mult = 1.0

        if mapped_action is None:
            result["errors"].append("unsupported_action")
            sanitized_decision["validation_errors"] = result["errors"]
            sanitized_decision["warnings"] = result["warnings"]
            result["decision"] = sanitized_decision
            return result

        if allowed_actions and mapped_action not in allowed_actions:
            result["errors"].append(f"action_not_allowed:{mapped_action.value}")
            sanitized_decision["validation_errors"] = result["errors"]
            sanitized_decision["warnings"] = result["warnings"]
            result["decision"] = sanitized_decision
            return result

        quantity = float(decision.get("quantity", 0.0) or 0.0)
        config = self.config

        if mapped_action in {Action.BUY_INITIAL, Action.BUY_REFILL}:
            max_size = float(getattr(config, "max_position_size", 0.0) or 0.0)
            available = float("inf") if max_size <= 0 else max(0.0, max_size - position_state.quantity)
            if mapped_action == Action.BUY_REFILL:
                last_sell = float(position_state.last_sell_qty or self.trade_engine._last_sell_quantity)
                if last_sell > 0:
                    available = min(available, last_sell)
            quantity = min(quantity, available)
            if quantity <= 0:
                result["errors"].append("buy_quantity_capped")
                sanitized_decision["validation_errors"] = result["errors"]
                sanitized_decision["warnings"] = result["warnings"]
                result["decision"] = sanitized_decision
                return result

        if mapped_action in {Action.SELL_PARTIAL, Action.SELL_ALL}:
            max_sell = float(position_state.quantity)
            if max_sell <= 0:
                result["errors"].append("no_position_to_sell")
                sanitized_decision["validation_errors"] = result["errors"]
                sanitized_decision["warnings"] = result["warnings"]
                result["decision"] = sanitized_decision
                return result
            if mapped_action == Action.SELL_ALL:
                quantity = max_sell
            else:
                quantity = min(quantity, max_sell)
                if quantity <= 0:
                    result["errors"].append("sell_quantity_none")
                    sanitized_decision["validation_errors"] = result["errors"]
                    sanitized_decision["warnings"] = result["warnings"]
                    result["decision"] = sanitized_decision
                    return result

        if mapped_action == Action.WITHDRAW_CAPITAL:
            quantity = float(position_state.remaining_capital)
            if quantity <= 0:
                result["errors"].append("no_capital_to_withdraw")
                sanitized_decision["validation_errors"] = result["errors"]
                sanitized_decision["warnings"] = result["warnings"]
                result["decision"] = sanitized_decision
                return result

        side = str(decision.get("side", "long")).lower()
        if side not in {"long", "short"}:
            side = "long"
        sanitized_decision["side"] = side

        quantity *= risk_mult
        sanitized_decision["risk_adjusted_quantity"] = quantity
        if quantity <= 0:
            result["warnings"].append("quantity_zero_after_ta")
            sanitized_decision["validation_errors"] = result["errors"]
            sanitized_decision["warnings"] = result["warnings"]
            sanitized_decision["action_override"] = "SKIP"
            result["decision"] = sanitized_decision
            result["leverage_eval"] = {
                "L_proposed": float(decision.get("leverage", 1.0) or 1.0),
                "L_final": 0.0,
                "L_suggest": 0.0,
                "L0_cap": 0.0,
                "liq_price_est": 0.0,
                "atr_norm": 0.0,
                "fusion_score": 0.0,
            }
            return result

        margin_mode_value = decision.get("margin_mode")
        if margin_mode_value not in {"isolated", "cross"}:
            margin_mode_value = "isolated" if self.config.prefer_isolated_margin else "cross"
            if "margin_mode" not in decision:
                result["warnings"].append("margin_mode_defaulted")
        sanitized_decision["margin_mode"] = margin_mode_value

        leverage_proposed = float(decision.get("leverage", 1.0) or 1.0) * L_mult
        sanitized_decision["leverage_proposed"] = leverage_proposed
        if "leverage" not in decision:
            result["warnings"].append("leverage_defaulted")

        stop_loss_value = decision.get("stop_loss")
        if stop_loss_value is None:
            stop_loss_value = self._default_stop_loss(price, side)
            sanitized_decision["stop_loss_auto"] = True
            result["warnings"].append("stop_loss_inferred")
        stop_loss_value = float(stop_loss_value)
        sanitized_decision["stop_loss"] = stop_loss_value

        equity_est = self._estimate_equity(position_state, price)
        atr_norm = self._compute_atr_norm(bars_by_level, price)
        fusion_score = self._extract_fusion_score(structure, extras)
        confidence_val = float(decision.get("confidence", 0.5) or 0.0)
        remaining_capital = max(position_state.remaining_capital, 0.0)

        leverage_eval: Dict[str, float]
        leverage_to_use = 1.0
        liq_est = position_state.liquidation_price or 0.0

        if self.config.use_leverage and mapped_action in {Action.BUY_INITIAL, Action.BUY_REFILL}:
            leverage_eval = combine_leverage(
                entry=price,
                stop=stop_loss_value,
                side=side,
                remaining_capital=remaining_capital if remaining_capital > 0 else equity_est,
                equity=equity_est,
                atr_norm=atr_norm,
                fusion_score=fusion_score,
                confidence=confidence_val,
                cfg=self.config,
            )
            L_suggest = leverage_eval["L_suggest"]
            L_cap = leverage_eval["L0_cap"]
            L_safe = leverage_eval["L_safe"]
            leverage_to_use = max(
                1.0,
                min(
                    leverage_proposed,
                    L_suggest,
                    L_cap,
                    L_safe,
                    self.config.exch_max_leverage,
                    self.config.max_leverage_config,
                ),
            )
            leverage_to_use = self._round_leverage(leverage_to_use)
            liq_est = estimate_liq_price(price, side, leverage_to_use, self.config.exch_maint_margin)
            leverage_eval.update(
                {
                    "L_proposed": leverage_proposed,
                    "L_final": leverage_to_use,
                    "liq_price_est": liq_est,
                    "atr_norm": atr_norm,
                    "fusion_score": fusion_score,
                }
            )
        else:
            leverage_to_use = leverage_proposed if self.config.use_leverage else 1.0
            leverage_eval = {
                "L_proposed": leverage_proposed,
                "L_suggest": leverage_to_use,
                "L0_cap": self.config.max_leverage_config,
                "L_safe": self.config.max_leverage_config,
                "L_final": leverage_to_use,
                "liq_price_est": liq_est,
                "atr_norm": atr_norm,
                "fusion_score": fusion_score,
            }

        sanitized_decision["leverage_final"] = leverage_to_use
        sanitized_decision["liquidation_price_est"] = liq_est

        plan_dict = {
            "action": mapped_action,
            "quantity": quantity,
            "leverage": leverage_to_use if self.config.use_leverage else None,
            "margin_mode": margin_mode_value if self.config.use_leverage else None,
            "stop_loss": stop_loss_value,
            "side": side,
        }

        order_result = self._execute_plan(plan_dict, price)
        if order_result is not None:
            result["executed"] = True
            result["order_result"] = asdict(order_result)
            result["quantity"] = quantity
            if self.config.use_leverage:
                position_state.current_leverage = leverage_to_use
                position_state.margin_mode = margin_mode_value
                position_state.liquidation_price = liq_est
            if position_state.equity is None:
                position_state.equity = equity_est
        else:
            result["order_result"] = None

        sanitized_decision["effective_quantity"] = quantity
        sanitized_decision["validation_errors"] = result["errors"]
        sanitized_decision["warnings"] = result["warnings"]
        sanitized_decision["leverage_eval"] = leverage_eval
        result["decision"] = sanitized_decision
        result["leverage_eval"] = leverage_eval
        return result

    @staticmethod
    def _map_prompt_action(action: str) -> Optional[Action]:
        normalized = action.strip().lower()
        mapping = {
            "hold": Action.HOLD,
            "wait": Action.HOLD,
            "open": Action.BUY_INITIAL,
            "buy_initial": Action.BUY_INITIAL,
            "buy": Action.BUY_REFILL,
            "buy_same": Action.BUY_REFILL,
            "add": Action.BUY_REFILL,
            "reduce": Action.SELL_PARTIAL,
            "sell_part": Action.SELL_PARTIAL,
            "sell_partial": Action.SELL_PARTIAL,
            "sell": Action.SELL_PARTIAL,
            "close": Action.SELL_ALL,
            "sell_all": Action.SELL_ALL,
            "exit": Action.SELL_ALL,
            "withdraw": Action.WITHDRAW_CAPITAL,
            "withdraw_capital": Action.WITHDRAW_CAPITAL,
        }
        return mapping.get(normalized, Action.HOLD if normalized == "" else None)

    def _parse_allowed_actions(self, allowed: Optional[Any]) -> Set[Action]:
        actions: Set[Action] = set()
        if not allowed:
            return actions
        if isinstance(allowed, (set, list, tuple)):
            iterable = allowed
        else:
            iterable = [allowed]
        for item in iterable:
            try:
                if isinstance(item, Action):
                    actions.add(item)
                else:
                    actions.add(Action(str(item)))
            except ValueError:
                continue
        return actions

    def _serialize_trade_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        serialized: Dict[str, Any] = {}
        for key, value in plan.items():
            if isinstance(value, Action):
                serialized[key] = value.value
            elif isinstance(value, set):
                serialized[key] = [item.value if isinstance(item, Action) else str(item) for item in value]
            else:
                serialized[key] = value
        if "allowed_actions" not in serialized:
            serialized["allowed_actions"] = []
        return serialized

    def _round_leverage(self, value: float) -> float:
        step = max(0.0, self.config.leverage_step)
        if step <= 0:
            return max(1.0, value)
        return max(step, math.floor(value / step) * step)

    def _default_stop_loss(self, price: float, side: str) -> float:
        distance_pct = max(self.config.min_stop_distance_pct * 1.5, 0.001)
        if side == "short":
            return price * (1.0 + distance_pct)
        return price * (1.0 - distance_pct)

    def _estimate_equity(self, position_state: PositionState, price: float) -> float:
        if position_state.equity is not None:
            return position_state.equity
        return position_state.remaining_capital + position_state.quantity * price

    def _compute_atr_norm(self, bars_by_level: Dict[str, List[Bar]], price: float) -> float:
        period = max(1, getattr(self.config, "atr_period", 14))
        bars: Optional[List[Bar]] = None
        for level in self.levels:
            candidate = bars_by_level.get(level)
            if candidate:
                bars = candidate
                break
        if not bars or len(bars) < 2:
            return max(self.config.min_stop_distance_pct, self.config.atr_vol_norm)
        lookback = bars[-(period + 1) :]
        if len(lookback) <= 1:
            return max(self.config.min_stop_distance_pct, self.config.atr_vol_norm)
        trs: List[float] = []
        prev_close = lookback[0].close
        for bar in lookback[1:]:
            tr = max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))
            trs.append(tr)
            prev_close = bar.close
        if not trs:
            return max(self.config.min_stop_distance_pct, self.config.atr_vol_norm)
        atr = sum(trs) / len(trs)
        return max(self.config.min_stop_distance_pct, atr / max(price, 1e-9))

    def _extract_fusion_score(self, structure: StructureState, extras: Dict[str, Any]) -> float:
        default_score = 0.5
        summary = extras.get("relation_summary")
        if isinstance(summary, dict):
            for key in ("score", "fusion_score", "resonance_score"):
                value = summary.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
        relation_matrix = getattr(structure, "relation_matrix", None)
        if isinstance(relation_matrix, dict):
            value = relation_matrix.get("score")
            if isinstance(value, (int, float)):
                return float(value)
        return default_score

    def _get_trading_research(
        self,
        *,
        symbol: str,
        signal: str,
        structure: StructureState,
        extras: Dict[str, Any],
        position_state: PositionState,
        price: float,
    ) -> Tuple[Optional[ResearchPacket], Optional[Dict[str, Any]], Dict[str, ResearchItem]]:
        if self.ta_manager is None or not self.ta_manager.enabled:
            return None, None, {}

        structure_packet = self._build_structure_packet(
            symbol=symbol,
            signal=signal,
            structure=structure,
            extras=extras,
            position_state=position_state,
            price=price,
        )
        stage = getattr(position_state, "cost_stage", position_state.stage)
        packet, _ = self.ta_manager.get_research(symbol, structure_packet, stage)
        if packet is None:
            return None, None, {}
        packet_dict = packet.to_dict()
        items_map = {item.symbol.upper(): item for item in packet.analysis}
        return packet, packet_dict, items_map

    def _build_structure_packet(
        self,
        *,
        symbol: str,
        signal: str,
        structure: StructureState,
        extras: Dict[str, Any],
        position_state: PositionState,
        price: float,
    ) -> Dict[str, Any]:
        payload = build_structure_payload(structure, levels=self.levels)
        position_snapshot = build_position_payload(position_state)
        return {
            "symbol": symbol,
            "signal": signal,
            "price": price,
            "stage": getattr(position_state, "cost_stage", position_state.stage),
            "position_stage": position_state.stage,
            "structure": payload,
            "extras": extras,
            "position": position_snapshot,
            "generated_at": time.time(),
        }
