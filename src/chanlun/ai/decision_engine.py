from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

from chanlun import config, fun
from chanlun.ai.prompt import TRADING_SYSTEM_PROMPT, generate_user_prompt
from chanlun.ai.market_state_ib import (
    collect_account_snapshot,
    collect_market_snapshot,
    collect_chanlun_snapshot,
    MarketSnapshot,
    AccountSnapshot,
    ChanlunSnapshot,
)

logger = fun.get_logger("ai_trader.log")


@dataclass
class TradeDecision:
    operation: str
    amount: Optional[float] = None
    leverage: Optional[float] = None
    percentage: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reasoning: str = ""


def _default_decision(reason: str = "AI disabled") -> TradeDecision:
    return TradeDecision(operation="HOLD", reasoning=reason)


def request_trading_decision(
    symbol: str,
    start_time,
    market_snapshot: Optional[MarketSnapshot] = None,
    account_snapshot: Optional[AccountSnapshot] = None,
    chanlun_snapshot: Optional[ChanlunSnapshot] = None,
) -> TradeDecision:
    snapshot = market_snapshot or collect_market_snapshot(symbol)
    account = account_snapshot or collect_account_snapshot()
    chanlun = chanlun_snapshot or collect_chanlun_snapshot(symbol)

    if snapshot is None:
        return _default_decision("insufficient market data")

    user_prompt = generate_user_prompt(
        snapshot.to_dict(),
        account.to_dict(),
        start_time,
        chanlun_snapshot=chanlun.to_dict() if chanlun else None,
    )

    if not config.AI_TOKEN:
        logger.warning("AI_TOKEN not configured, returning default HOLD decision")
        return _default_decision("AI token missing")

    model = getattr(config, "AI_MODEL", None) or "gpt-4o-mini"

    client = OpenAI(api_key=config.AI_TOKEN)

    schema = {
        "name": "trading_decision",
        "schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["BUY", "SELL", "HOLD"],
                },
                "amount": {"type": "number"},
                "leverage": {"type": "number"},
                "percentage": {"type": "number"},
                "stopLoss": {"type": "number"},
                "takeProfit": {"type": "number"},
                "chat": {"type": "string"},
            },
            "required": ["operation"],
            "additionalProperties": False,
        },
    }

    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": TRADING_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_schema", "json_schema": schema},
        )
        content = response.output[0].content[0].text  # type: ignore
        data = json.loads(content)
        decision = TradeDecision(
            operation=data.get("operation", "HOLD"),
            amount=data.get("amount"),
            leverage=data.get("leverage"),
            percentage=data.get("percentage"),
            stop_loss=data.get("stopLoss"),
            take_profit=data.get("takeProfit"),
            reasoning=data.get("chat", ""),
        )
        logger.info("AI decision: %s", decision)
        return decision
    except Exception as exc:
        logger.error("AI decision error: %s", exc)
        return _default_decision(f"AI error: {exc}")
