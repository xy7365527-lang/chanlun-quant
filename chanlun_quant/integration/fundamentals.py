from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Dict, Optional

from external.trading_agents.tradingagents.dataflows.alpha_vantage_fundamentals import (
    get_fundamentals as alpha_get_fundamentals,
)

logger = logging.getLogger(__name__)


def _safe_float(value: Optional[str]) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=256)
def get_fundamentals(symbol: str) -> Dict[str, Any]:
    """
    通过 Alpha Vantage API 获取基础面数据（需设置 ALPHA_VANTAGE_API_KEY）。
    """
    symbol = symbol.upper()
    try:
        raw = alpha_get_fundamentals(symbol)
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception as exc:
        logger.warning("获取 %s 基本面数据失败: %s", symbol, exc)
        return {}

    if not isinstance(data, dict):
        logger.warning("Alpha Vantage 返回未知格式: %s", data)
        return {}

    return {
        "pe": _safe_float(data.get("PERatio")),
        "market_cap": _safe_float(data.get("MarketCapitalization")),
        "sector": data.get("Sector"),
        "industry": data.get("Industry"),
        "beta": _safe_float(data.get("Beta")),
        "dividend_yield": _safe_float(data.get("DividendYield")),
    }


__all__ = ["get_fundamentals"]
