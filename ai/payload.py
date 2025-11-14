from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict


def build_ai_context(structure_state, position_state, cfg) -> Dict[str, Any]:
    """Aggregate structure, momentum, and risk context for downstream LLM usage."""
    return {
        "symbol": getattr(cfg, "symbol", "UNKNOWN"),
        "levels": structure_state.levels,
        "trends": structure_state.trends,
        "signals": {lv: [asdict(sig) for sig in sigs] for lv, sigs in structure_state.signals.items()},
        "centrals": structure_state.centrals,
        "relations": structure_state.relations,
        "position": asdict(position_state),
        "stage": getattr(position_state, "stage", "INITIAL"),
        "risk_limits": {
            "max_leverage": getattr(cfg, "max_leverage", 1.0),
            "max_position": getattr(cfg, "max_position", 10_000),
            "max_notional": getattr(cfg, "max_notional", 1_000_000),
            "cooldown_bars": getattr(cfg, "cooldown_bars", 3),
        },
        "action_space": {
            "allowed": ["BUY", "SELL", "HOLD"],
            "min_qty": getattr(cfg, "min_qty", 1),
            "step_qty": getattr(cfg, "step_qty", 1),
        },
        "macd_area_mode": getattr(cfg, "macd_area_mode", "hist"),
    }


ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
        "quantity": {"type": "number", "minimum": 0},
        "leverage": {"type": "number", "minimum": 0},
        "reason": {"type": "string"},
    },
    "required": ["action", "quantity"],
    "additionalProperties": False,
}


def validate_ai_instruction(instr: Dict[str, Any], position_state, cfg) -> tuple[bool, list[str]]:
    """Validate LLM instruction against structural constraints and risk limits."""
    errors: list[str] = []
    if instr.get("action") not in {"BUY", "SELL", "HOLD"}:
        errors.append("invalid action")

    qty = instr.get("quantity")
    if not isinstance(qty, (int, float)) or qty < 0:
        errors.append("invalid quantity")
        qty = 0

    stage = getattr(position_state, "stage", "INITIAL")
    action = instr.get("action")
    position_qty = getattr(position_state, "quantity", 0)
    if stage == "INITIAL" and action == "SELL":
        errors.append("cannot SELL in INITIAL stage")
    if action == "SELL" and qty > position_qty:
        errors.append("sell qty exceeds position")
    max_position = getattr(cfg, "max_position", 10_000)
    if action == "BUY" and (position_qty + qty) > max_position:
        errors.append("buy exceeds max_position")

    return len(errors) == 0, errors


def to_ib_order(instr: Dict[str, Any], cfg) -> Dict[str, Any]:
    """Translate validated instruction into interactive-brokers style order parameters."""
    side = "BUY" if instr["action"] == "BUY" else "SELL"
    return {
        "side": side,
        "quantity": int(instr["quantity"]),
        "orderType": "MKT",
        "tif": "DAY",
        "symbol": getattr(cfg, "symbol", "UNKNOWN"),
    }


def allowed_action_space(stage, position_state, cfg) -> Dict[str, object]:
    """Return permissible actions and quantity caps under the current trading stage."""
    stage = stage or getattr(position_state, "stage", "INITIAL")
    quantity = getattr(position_state, "quantity", 0)
    max_position = getattr(cfg, "max_position", 10_000)
    last_sell_qty = getattr(position_state, "last_sell_qty", 0)

    space: Dict[str, object] = {
        "BUY": True,
        "SELL": True,
        "HOLD": True,
        "max_buy_qty": max_position - quantity,
        "max_sell_qty": quantity,
    }

    if stage == "INITIAL":
        space["SELL"] = False
        space["max_sell_qty"] = 0
    elif stage == "PARTIAL_SOLD":
        space["SELL"] = False
        space["max_sell_qty"] = 0
        space["max_buy_qty"] = min(space["max_buy_qty"], last_sell_qty or 0)
    elif stage == "PROFIT_HOLD":
        space["max_buy_qty"] = min(space["max_buy_qty"], max_position * 0.2)
        space["max_sell_qty"] = min(space["max_sell_qty"], quantity * 0.3)

    space["max_buy_qty"] = max(0.0, float(space["max_buy_qty"]))
    space["max_sell_qty"] = max(0.0, float(space["max_sell_qty"]))
    return space
