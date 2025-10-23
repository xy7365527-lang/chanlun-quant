from __future__ import annotations

import datetime
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from chanlun import fun
from chanlun.cl_utils import query_cl_chart_config, web_batch_get_cl_datas
from chanlun.exchange.exchange_polygon import ExchangePolygon


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(0)


@dataclass
class MarketSnapshot:
    symbol: str
    last_price: float
    ema_fast: float
    ema_slow: float
    rsi: float
    closes: List[float]
    timestamps: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AccountSnapshot:
    available_funds: float
    net_liquidation: float
    buying_power: float
    positions: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ChanlunSnapshot:
    frequency: str
    last_bi: Dict[str, Any]
    last_xd: Dict[str, Any]
    last_zs: Dict[str, Any]
    signals: Dict[str, Any]
    macd: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _prepare_dataframe(
    df: Optional[pd.DataFrame], limit: int = 200
) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return None
    df = df.copy()
    df.sort_values("date", inplace=True)
    if limit and len(df) > limit:
        df = df.iloc[-limit:]
    df.reset_index(drop=True, inplace=True)
    return df


def collect_market_snapshot(
    symbol: str,
    exchange: Optional[ExchangePolygon] = None,
    frequency: str = "60m",
) -> Optional[MarketSnapshot]:
    ex = exchange or ExchangePolygon()
    df = _prepare_dataframe(ex.klines(symbol, frequency))
    if df is None or len(df) < 10:
        return None

    closes = pd.Series(df["close"].astype(float))
    ema_fast_series = _ema(closes, 20)
    ema_slow_series = _ema(closes, 50)
    rsi_series = _rsi(closes, 14)

    return MarketSnapshot(
        symbol=symbol.upper(),
        last_price=float(closes.iloc[-1]),
        ema_fast=float(ema_fast_series.iloc[-1]),
        ema_slow=float(ema_slow_series.iloc[-1]),
        rsi=float(rsi_series.iloc[-1]),
        closes=[float(v) for v in closes.tolist()],
        timestamps=[
            datetime.datetime.fromtimestamp(pd.Timestamp(ts).timestamp()).isoformat()
            for ts in df["date"].tolist()
        ],
    )


def collect_account_snapshot(
    exchange: Optional[ExchangePolygon] = None,
) -> AccountSnapshot:
    ex = exchange or ExchangePolygon()

    # polygon REST API does not offer brokerage account data, so fill sensible defaults
    try:
        balance = ex.balance() or {}
    except Exception:
        balance = {}

    try:
        positions = ex.positions() or []
    except Exception:
        positions = []

    buying_power = float(
        balance.get("BuyingPower") or balance.get("BuyingPowerS", 0) or 0
    )

    formatted_positions: List[Dict[str, Any]] = []
    for pos in positions:
        try:
            formatted_positions.append(
                {
                    "code": str(pos.get("code")),
                    "position": float(pos.get("position", 0)),
                    "avgCost": float(pos.get("avgCost", 0)),
                    "marketPrice": float(pos.get("marketPrice", 0)),
                    "unrealizedPnl": float(
                        pos.get("unrealizedPNL", 0)
                        or pos.get("unrealizedPnl", 0)
                        or 0
                    ),
                }
            )
        except Exception:
            continue

    if not balance and not formatted_positions:
        # Gracefully provide placeholders when brokerage data is unavailable
        formatted_positions = []
        balance = {
            "AvailableFunds": 0.0,
            "NetLiquidation": 0.0,
        }

    return AccountSnapshot(
        available_funds=float(balance.get("AvailableFunds") or 0),
        net_liquidation=float(balance.get("NetLiquidation") or 0),
        buying_power=buying_power,
        positions=formatted_positions,
    )


def collect_chanlun_snapshot(
    symbol: str,
    exchange: Optional[ExchangePolygon] = None,
    frequency: str = "60m",
    cl_config: Optional[Dict[str, Any]] = None,
) -> Optional[ChanlunSnapshot]:
    ex = exchange or ExchangePolygon()
    klines = _prepare_dataframe(ex.klines(symbol, frequency))
    if klines is None or len(klines) < 20:
        return None

    cfg = cl_config or query_cl_chart_config("us", symbol)
    try:
        cds = web_batch_get_cl_datas("us", symbol, {frequency: klines}, cfg)
    except Exception:
        return None

    if not cds:
        return None

    cd = cds[0]
    idx = cd.get_idx() or {}
    macd_idx = idx.get("macd", {})

    def _last(series):
        if isinstance(series, (list, tuple)) and series:
            return float(series[-1])
        return 0.0

    macd_info = {
        "dif": _last(macd_idx.get("dif")),
        "dea": _last(macd_idx.get("dea")),
        "hist": _last(macd_idx.get("hist")),
    }

    def _format_bi(bi):
        if bi is None:
            return {}
        return {
            "type": getattr(bi, "type", ""),
            "done": bi.is_done() if hasattr(bi, "is_done") else False,
            "length": bi.fx_num() if hasattr(bi, "fx_num") else 0,
            "high": getattr(bi, "high", None),
            "low": getattr(bi, "low", None),
            "mmds": [m.name for m in bi.get_mmds()] if hasattr(bi, "get_mmds") else [],
            "bcs": [b.type for b in bi.get_bcs()] if hasattr(bi, "get_bcs") else [],
        }

    def _format_xd(xd):
        if xd is None:
            return {}
        return {
            "type": getattr(xd, "type", ""),
            "length": xd.fx_num() if hasattr(xd, "fx_num") else 0,
            "high": getattr(xd, "high", None),
            "low": getattr(xd, "low", None),
            "done": xd.is_done() if hasattr(xd, "is_done") else False,
        }

    def _format_zs(zs):
        if zs is None:
            return {}
        return {
            "type": getattr(zs, "type", ""),
            "level": getattr(zs, "level", None),
            "zg": getattr(zs, "zg", None),
            "zd": getattr(zs, "zd", None),
            "gg": getattr(zs, "gg", None),
            "dd": getattr(zs, "dd", None),
            "done": getattr(zs, "done", None),
        }

    bis = cd.get_bis()
    last_bi = _format_bi(bis[-1] if bis else None)

    xds = cd.get_xds()
    last_xd = _format_xd(xds[-1] if xds else None)

    last_zs = _format_zs(cd.get_last_bi_zs())

    signals = {
        "bi_mmd_count": len(last_bi.get("mmds", [])),
        "bi_bc_count": len(last_bi.get("bcs", [])),
    }

    return ChanlunSnapshot(
        frequency=frequency,
        last_bi=last_bi,
        last_xd=last_xd,
        last_zs=last_zs,
        signals=signals,
        macd=macd_info,
    )

