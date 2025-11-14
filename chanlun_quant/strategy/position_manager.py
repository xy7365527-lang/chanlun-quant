from __future__ import annotations

from typing import Literal

from chanlun_quant.types import CostStageType, PositionState

StageType = Literal["INITIAL", "HOLDING", "PARTIAL_SOLD", "PROFIT_HOLD", "EXIT"]


class HoldingManager:
    """Manage cost basis and stage transitions for a single position."""

    def __init__(self, initial_capital: float = 0.0, initial_quantity: float = 0.0) -> None:
        self.state = PositionState()
        if initial_quantity > 0 and initial_capital > 0:
            avg_price = initial_capital / initial_quantity
            self.state = PositionState(
                quantity=initial_quantity,
                avg_cost=avg_price,
                book_cost=initial_capital,
                realized_profit=0.0,
                initial_capital=initial_capital,
                remaining_capital=0.0,
                withdrawn_capital=0.0,
                initial_quantity=initial_quantity,
                stage="HOLDING",
                cost_stage="COST_DOWN",
                initial_avg_cost=avg_price,
                last_action="BUY_INITIAL",
            )
        self._update_cost_metrics()
        self._sync_stage()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def buy(self, price: float, quantity: float, *, is_initial_buy: bool = False) -> None:
        if quantity <= 0 or price <= 0:
            return

        cost = price * quantity
        if self.state.quantity == 0:
            if not is_initial_buy and self.cost_covered():
                self._apply_free_ride_buy(cost, quantity)
            else:
                self._reset_position(price, quantity, cost, is_initial_buy)
            return

        self._augment_position(price, quantity, cost, is_initial_buy)

    def sell(self, price: float, quantity: float) -> None:
        if quantity <= 0 or price <= 0 or self.state.quantity <= 0:
            return

        sell_qty = min(quantity, self.state.quantity)
        proceeds = price * sell_qty

        current_qty = self.state.quantity
        cost_per_share = self.state.book_cost / current_qty if current_qty > 0 else 0.0

        principal_released = cost_per_share * sell_qty
        profit = proceeds - principal_released

        self.state.quantity -= sell_qty
        self.state.book_cost = max(self.state.book_cost - principal_released, 0.0)
        self.state.remaining_capital += principal_released
        self.state.realized_profit += profit
        self.state.last_sell_qty = sell_qty
        self.state.last_action = "SELL"

        self._recalculate_cost(price)

    def withdraw_capital(self) -> float:
        amount = max(self.state.remaining_capital, 0.0)
        if amount <= 0:
            return 0.0
        self.state.withdrawn_capital += amount
        self.state.remaining_capital = 0.0
        self.state.free_ride = True
        self.state.last_action = "WITHDRAW"
        self._update_cost_metrics()
        self._sync_stage()
        return amount

    def cost_covered(self) -> bool:
        return self.state.free_ride or self.state.cost_coverage_ratio >= 1.0

    def current_value(self, market_price: float) -> float:
        if market_price <= 0:
            market_price = 0.0
        return self.state.quantity * market_price + self.state.remaining_capital

    def reset(self) -> None:
        self.state = PositionState()
        self._update_cost_metrics()
        self._sync_stage()

    def get_current_stage(self) -> StageType:
        return self.state.stage  # type: ignore[return-value]

    def get_position_state(self) -> PositionState:
        return self.state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _reset_position(self, price: float, quantity: float, cost: float, is_initial_buy: bool) -> None:
        self.state = PositionState(
            quantity=quantity,
            avg_cost=price,
            book_cost=cost,
            realized_profit=0.0,
            initial_capital=cost,
            remaining_capital=0.0,
            withdrawn_capital=0.0,
            initial_quantity=quantity,
            stage="HOLDING",
            cost_stage="COST_DOWN",
            initial_avg_cost=price,
            last_action="BUY_INITIAL" if is_initial_buy else "BUY_RESET",
        )
        self._update_cost_metrics()
        self._sync_stage()

    def _apply_free_ride_buy(self, cost: float, quantity: float) -> None:
        # Use realised profits to finance the position; principal remains separate.
        self.state.realized_profit = max(self.state.realized_profit - cost, 0.0)
        self.state.quantity = quantity
        self.state.book_cost = 0.0
        self.state.avg_cost = 0.0
        self.state.initial_capital = 0.0
        self.state.initial_quantity = max(self.state.initial_quantity, quantity)
        self.state.last_sell_qty = 0.0
        self.state.free_ride = True
        self.state.cost_stage = "NEG_COST"
        self.state.initial_avg_cost = 0.0
        self.state.last_action = "BUY_FREE"
        self._update_cost_metrics()
        self._sync_stage()

    def _augment_position(self, price: float, quantity: float, cost: float, is_initial_buy: bool) -> None:
        principal_used = min(cost, self.state.remaining_capital)
        profit_used = max(cost - principal_used, 0.0)

        self.state.remaining_capital -= principal_used
        self.state.realized_profit -= profit_used
        self.state.book_cost += principal_used
        self.state.quantity += quantity

        self._recalculate_cost(price)
        if self.state.initial_avg_cost == 0.0:
            self.state.initial_avg_cost = self.state.avg_cost
        self.state.last_action = "BUY_REFILL" if not is_initial_buy else "BUY_INITIAL"

    def _recalculate_cost(self, reference_price: float) -> None:
        self.state.book_cost = max(self.state.book_cost, 0.0)
        self.state.quantity = max(self.state.quantity, 0.0)

        if self.state.quantity > 0:
            profit_excess = max(self.state.realized_profit - self.state.remaining_capital, 0.0)
            effective_cost = max(self.state.book_cost - profit_excess, 0.0)
            self.state.avg_cost = effective_cost / self.state.quantity
        else:
            self.state.avg_cost = 0.0
            self.state.book_cost = 0.0

        self.state.initial_quantity = max(self.state.initial_quantity, self.state.quantity)
        self._update_cost_metrics()
        self._sync_stage()

    def _sync_stage(self) -> None:
        if self.state.quantity <= 0:
            self.state.stage = "INITIAL"
            self.state.free_ride = False
            return

        if self.cost_covered():
            self.state.stage = "PROFIT_HOLD"
            self.state.free_ride = True
            return

        if self.state.initial_quantity > 0 and self.state.quantity < self.state.initial_quantity:
            self.state.stage = "PARTIAL_SOLD"
        else:
            self.state.stage = "HOLDING"

    def _update_cost_metrics(self) -> None:
        state = self.state

        if state.initial_capital > 0:
            recovered = min(state.initial_capital, state.remaining_capital + state.withdrawn_capital)
            state.principal_recovered = recovered
            state.cost_coverage_ratio = recovered / state.initial_capital if state.initial_capital > 0 else 0.0
        else:
            state.principal_recovered = state.remaining_capital + state.withdrawn_capital
            state.cost_coverage_ratio = 1.0 if state.free_ride or state.principal_recovered > 0 else 0.0

        if state.free_ride:
            state.cost_stage = "NEG_COST"
        elif state.initial_capital <= 0 and state.quantity <= 0:
            state.cost_stage = "INITIAL"
        elif state.withdrawn_capital >= state.initial_capital > 0:
            state.cost_stage = "WITHDRAW"
        elif state.initial_capital > 0 and state.cost_coverage_ratio >= 1.0:
            state.cost_stage = "NEG_COST" if state.realized_profit > 0 else "ZERO_COST"
        else:
            state.cost_stage = "COST_DOWN" if state.quantity > 0 else "INITIAL"
