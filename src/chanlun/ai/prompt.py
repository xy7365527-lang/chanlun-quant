from __future__ import annotations

import datetime
from textwrap import dedent
from typing import Dict, Any, Optional


TRADING_SYSTEM_PROMPT = dedent(
    """
    You are an experienced US equities trader and portfolio manager.
    Analyse provided market snapshots and account information to recommend one of:
    BUY, SELL, or HOLD.

    When recommending BUY or SELL you may additionally propose:
      - leverage multiplier (>=1, <=3 by default)
      - position size in USD
      - optional stop loss / take profit prices
      - percentage of existing position to close when reducing risk

    Focus on risk-adjusted returns, capital preservation, and intraday conditions.
    Always output a structured JSON object matching the trading_decision schema.
    """
)


def generate_user_prompt(
    market_snapshot: Dict[str, Any],
    account_snapshot: Dict[str, Any],
    start_time: datetime.datetime,
    chanlun_snapshot: Optional[Dict[str, Any]] = None,
) -> str:
    now = datetime.datetime.utcnow()
    elapsed_minutes = int((now - start_time).total_seconds() // 60)

    market_section = "\n".join(
        [
            f"Symbol: {market_snapshot.get('symbol')}",
            f"Last price: {market_snapshot.get('last_price')}",
            f"EMA(20): {market_snapshot.get('ema_fast')}",
            f"EMA(50): {market_snapshot.get('ema_slow')}",
            f"RSI(14): {market_snapshot.get('rsi')}",
        ]
    )
    account_section = "\n".join(
        [
            f"Available funds: {account_snapshot.get('available_funds')}",
            f"Buying power: {account_snapshot.get('buying_power')}",
            f"Net liquidation: {account_snapshot.get('net_liquidation')}",
            f"Open positions: {account_snapshot.get('positions')}",
        ]
    )

    chanlun_section = ""
    if chanlun_snapshot:
        last_bi = chanlun_snapshot.get("last_bi", {})
        last_xd = chanlun_snapshot.get("last_xd", {})
        last_zs = chanlun_snapshot.get("last_zs", {})
        macd = chanlun_snapshot.get("macd", {})
        signals = chanlun_snapshot.get("signals", {})

        chanlun_section = dedent(
            f"""
            ### CHANLUN SNAPSHOT ({chanlun_snapshot.get('frequency')})
            Last BI: {last_bi}
            Last XD: {last_xd}
            Last ZS: {last_zs}
            MACD: {macd}
            Signals: {signals}
            """
        )

    return dedent(
        f"""
        It has been {elapsed_minutes} minutes since trading session start.
        Current UTC time: {now.isoformat()}.

        ### MARKET SNAPSHOT
        {market_section}

        ### ACCOUNT SNAPSHOT
        {account_section}

        {chanlun_section}

        Provide your analysis and recommendation.
        """
    ).strip()
