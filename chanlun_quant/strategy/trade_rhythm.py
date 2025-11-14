from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional, Set

from chanlun_quant.strategy.position_manager import HoldingManager, StageType
from chanlun_quant.types import CostStageType


class State(Enum):
    INITIAL = "INITIAL"
    HOLDING = "HOLDING"
    PARTIAL_SOLD = "PARTIAL_SOLD"
    PROFIT_HOLD = "PROFIT_HOLD"
    EXIT = "EXIT"


class Action(Enum):
    HOLD = "HOLD"
    BUY_INITIAL = "BUY_INITIAL"
    SELL_PARTIAL = "SELL_PARTIAL"
    BUY_REFILL = "BUY_REFILL"
    SELL_ALL = "SELL_ALL"
    WITHDRAW_CAPITAL = "WITHDRAW_CAPITAL"


class TradeRhythmEngine:
    """Stage-driven trading rhythm engine."""

    def __init__(self, initial_capital: float = 0.0, initial_quantity: float = 0.0) -> None:
        self.holding_manager = HoldingManager(initial_capital=initial_capital, initial_quantity=initial_quantity)
        self.state: State = State.INITIAL
        self._last_sell_quantity: float = 0.0
        self._synthetic_quantity: float = initial_quantity
        self.cost_stage: CostStageType = self.holding_manager.state.cost_stage
        self._last_cost_stage: CostStageType = self.cost_stage
        self._allowed_actions: Dict[CostStageType, Set[Action]] = {
            "INITIAL": {Action.HOLD, Action.BUY_INITIAL},
            "COST_DOWN": {Action.HOLD, Action.SELL_PARTIAL, Action.BUY_REFILL, Action.SELL_ALL},
            "ZERO_COST": {Action.HOLD, Action.SELL_PARTIAL, Action.BUY_REFILL, Action.SELL_ALL, Action.WITHDRAW_CAPITAL},
            "NEG_COST": {Action.HOLD, Action.SELL_PARTIAL, Action.SELL_ALL, Action.WITHDRAW_CAPITAL},
            "WITHDRAW": {Action.HOLD, Action.SELL_PARTIAL, Action.SELL_ALL},
        }

    def on_signal(self, signal_type: str, current_price: float, cfg: Any) -> Dict[str, Any]:
        current_stage = self._derive_state_from_manager()
        self._update_cost_stage()
        action_plan: Dict[str, Any] = {
            "stage": current_stage.value,
            "next_stage": current_stage.value,
            "cost_stage": self.cost_stage,
            "action": Action.HOLD,
            "quantity": 0.0,
            "reason": "No action",
            "allowed_actions": self._allowed_actions.get(self.cost_stage, {Action.HOLD}),
        }

        handler_map = {
            State.INITIAL: self._handle_initial,
            State.HOLDING: self._handle_holding,
            State.PARTIAL_SOLD: self._handle_partial_sold,
            State.PROFIT_HOLD: self._handle_profit_hold,
            State.EXIT: self._handle_exit,
        }
        handler = handler_map.get(current_stage)
        if handler:
            action_plan = handler(signal_type, current_price, cfg, action_plan)

        action_plan = self._apply_cost_stage_rules(action_plan, signal_type)
        self.state = State(action_plan["next_stage"])  # type: ignore[arg-type]
        return action_plan

    def get_current_stage(self) -> State:
        return self._derive_state_from_manager()

    def get_holding_manager(self) -> HoldingManager:
        return self.holding_manager

    # ------------------------------------------------------------------
    # State & stage helpers
    # ------------------------------------------------------------------
    def _derive_state_from_manager(self) -> State:
        stage_text: StageType = self.holding_manager.get_current_stage()
        try:
            derived = State(stage_text)
        except ValueError:
            derived = self.state
        if derived == State.INITIAL and self.state != State.INITIAL:
            return self.state
        return derived

    def _update_cost_stage(self) -> None:
        state = self.holding_manager.state
        self._last_cost_stage = self.cost_stage
        self.cost_stage = state.cost_stage
        if self.cost_stage == "INITIAL" and self._synthetic_quantity > 0:
            self.cost_stage = "COST_DOWN"

    def _apply_cost_stage_rules(self, action_plan: Dict[str, Any], signal_type: str) -> Dict[str, Any]:
        allowed = self._allowed_actions.get(self.cost_stage, {Action.HOLD})
        action_plan["allowed_actions"] = [item.value for item in allowed]

        action = action_plan["action"]
        if action not in allowed:
            action_plan.update({"action": Action.HOLD, "quantity": 0.0, "reason": f"Action {action.value} not allowed under {self.cost_stage}"})
            action = Action.HOLD

        position = self.holding_manager.state
        if self.cost_stage in {"ZERO_COST", "NEG_COST"} and position.remaining_capital > 0:
            action_plan.update(
                {
                    "action": Action.WITHDRAW_CAPITAL,
                    "quantity": position.remaining_capital,
                    "reason": "Principal recovered, withdraw",
                    "next_stage": self.state.value,
                }
            )
            return action_plan

        if self.cost_stage in {"NEG_COST", "WITHDRAW"} and action == Action.BUY_REFILL:
            action_plan.update({"action": Action.HOLD, "quantity": 0.0, "reason": "Forbidden to add during NEG_COST"})

        if self.cost_stage == "INITIAL" and action != Action.BUY_INITIAL:
            action_plan.update({"action": Action.HOLD, "quantity": 0.0, "reason": "Await initial BUY1"})

        if self.cost_stage == "COST_DOWN" and signal_type in {"SELL_ALL", "STOP_LOSS"}:
            qty = float(position.quantity or self._synthetic_quantity)
            if qty > 0:
                action_plan.update(
                    {
                        "action": Action.SELL_ALL,
                        "quantity": qty,
                        "reason": f"{signal_type} triggers full exit",
                        "next_stage": State.EXIT.value,
                    }
                )
        return action_plan

    # ------------------------------------------------------------------
    # Stage-specific handlers
    # ------------------------------------------------------------------
    def _handle_initial(self, signal_type: str, current_price: float, cfg: Any, action_plan: Dict[str, Any]) -> Dict[str, Any]:
        if signal_type == "BUY1":
            qty = float(getattr(cfg, "initial_buy_quantity", 0.0))
            if qty > 0:
                self._synthetic_quantity = qty
                action_plan.update(
                    {
                        "action": Action.BUY_INITIAL,
                        "quantity": qty,
                        "reason": "Initial BUY1 signal",
                        "next_stage": State.HOLDING.value,
                    }
                )
        return action_plan

    def _handle_holding(self, signal_type: str, current_price: float, cfg: Any, action_plan: Dict[str, Any]) -> Dict[str, Any]:
        holding_state = self.holding_manager.state
        base_quantity = holding_state.quantity or self._synthetic_quantity
        if signal_type == "SELL1":
            ratio = float(getattr(cfg, "partial_sell_ratio", 0.5))
            sell_qty = max(base_quantity * ratio, 0.0)
            if sell_qty > 0:
                self._last_sell_quantity = sell_qty
                self._synthetic_quantity = max(base_quantity - sell_qty, 0.0)
                action_plan.update(
                    {
                        "action": Action.SELL_PARTIAL,
                        "quantity": sell_qty,
                        "reason": "Partial take profit on SELL1",
                        "next_stage": State.PARTIAL_SOLD.value,
                    }
                )
        elif signal_type in {"SELL_ALL", "STOP_LOSS"}:
            sell_qty = holding_state.quantity or base_quantity
            if sell_qty > 0:
                self._synthetic_quantity = 0.0
                action_plan.update(
                    {
                        "action": Action.SELL_ALL,
                        "quantity": sell_qty,
                        "reason": f"Exit due to {signal_type}",
                        "next_stage": State.EXIT.value,
                    }
                )
        return action_plan

    def _handle_partial_sold(self, signal_type: str, current_price: float, cfg: Any, action_plan: Dict[str, Any]) -> Dict[str, Any]:
        holding_state = self.holding_manager.state
        if signal_type == "BUY1":
            buy_qty = self._last_sell_quantity or holding_state.last_sell_qty or self._synthetic_quantity
            if buy_qty > 0:
                self._synthetic_quantity += buy_qty
                action_plan.update(
                    {
                        "action": Action.BUY_REFILL,
                        "quantity": buy_qty,
                        "reason": "Refill after partial sell",
                        "next_stage": State.HOLDING.value,
                    }
                )
        elif signal_type in {"SELL_ALL", "STOP_LOSS"}:
            sell_qty = holding_state.quantity or self._synthetic_quantity
            if sell_qty > 0:
                self._synthetic_quantity = 0.0
                action_plan.update(
                    {
                        "action": Action.SELL_ALL,
                        "quantity": sell_qty,
                        "reason": f"Full exit due to {signal_type}",
                        "next_stage": State.EXIT.value,
                    }
                )
        return action_plan

    def _handle_profit_hold(self, signal_type: str, current_price: float, cfg: Any, action_plan: Dict[str, Any]) -> Dict[str, Any]:
        holding_state = self.holding_manager.state
        base_quantity = holding_state.quantity or self._synthetic_quantity
        if signal_type == "SELL1":
            ratio = float(getattr(cfg, "profit_sell_ratio", 0.3))
            sell_qty = max(base_quantity * ratio, 0.0)
            if sell_qty > 0:
                self._last_sell_quantity = sell_qty
                self._synthetic_quantity = max(base_quantity - sell_qty, 0.0)
                action_plan.update(
                    {
                        "action": Action.SELL_PARTIAL,
                        "quantity": sell_qty,
                        "reason": "Take profit while free riding",
                        "next_stage": State.PARTIAL_SOLD.value,
                    }
                )
        elif signal_type == "BUY1":
            default_qty = getattr(cfg, "profit_buy_quantity", 0.1 * self.holding_manager.state.initial_quantity)
            buy_qty = self._last_sell_quantity or holding_state.last_sell_qty or default_qty
            if buy_qty > 0:
                self._synthetic_quantity += buy_qty
                action_plan.update(
                    {
                        "action": Action.BUY_REFILL,
                        "quantity": buy_qty,
                        "reason": "Add size during profit hold",
                        "next_stage": State.PROFIT_HOLD.value,
                    }
                )
        elif signal_type in {"SELL_ALL", "STOP_LOSS"}:
            sell_qty = holding_state.quantity or self._synthetic_quantity
            if sell_qty > 0:
                self._synthetic_quantity = 0.0
                action_plan.update(
                    {
                        "action": Action.SELL_ALL,
                        "quantity": sell_qty,
                        "reason": f"Final exit due to {signal_type}",
                        "next_stage": State.EXIT.value,
                    }
                )
        return action_plan

    def _handle_exit(self, signal_type: str, current_price: float, cfg: Any, action_plan: Dict[str, Any]) -> Dict[str, Any]:
        if signal_type == "BUY1" and self.holding_manager.state.quantity <= 0:
            qty = float(getattr(cfg, "initial_buy_quantity", 0.0))
            if qty > 0:
                self._synthetic_quantity = qty
                action_plan.update(
                    {
                        "action": Action.BUY_INITIAL,
                        "quantity": qty,
                        "reason": "Restart cycle after exit",
                        "next_stage": State.HOLDING.value,
                    }
                )
        return action_plan
