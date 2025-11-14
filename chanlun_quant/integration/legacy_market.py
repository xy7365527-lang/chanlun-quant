from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

import pandas as pd
import pytz

from chanlun.cl_interface import ICL
from chanlun.cl_utils import query_cl_chart_config, web_batch_get_cl_datas

from chanlun_quant.types import Bar

__all__ = ["bars_to_dataframe", "LegacyKlinesView", "LegacyMarketDataBridge"]

_EMPTY_COLUMNS = ["date", "open", "high", "low", "close", "volume", "code"]
_CHINA_TZ = pytz.timezone("Asia/Shanghai")


def bars_to_dataframe(symbol: str, bars: Iterable[Bar]) -> pd.DataFrame:
    """
    Convert chanlun-quant ``Bar`` objects to the legacy dataframe format.

    Legacy CL 计算逻辑期望：
    - `date` 为本地时区（Asia/Shanghai）的 naive datetime；
    - `volume` 列对应旧对象中的 `a` 字段。
    """

    rows = []
    for bar in bars:
        ts = bar.timestamp
        if ts.tzinfo is None:
            ts = _CHINA_TZ.localize(ts)
        ts = ts.astimezone(_CHINA_TZ).replace(tzinfo=None)
        rows.append(
            {
                "date": ts,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "code": symbol,
            }
        )
    if not rows:
        return pd.DataFrame(columns=_EMPTY_COLUMNS)
    df = pd.DataFrame(rows, columns=_EMPTY_COLUMNS)
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


class LegacyKlinesView:
    """
    Minimal ``MarketDatas``-like facade backed by Bar objects.

    适用于只需要 `klines` 的轻量级策略（如 `StrategyTest`）。
    """

    def __init__(self, frequencys: Sequence[str]) -> None:
        self.frequencys = list(frequencys)
        self._frames: Dict[str, pd.DataFrame] = {
            freq: pd.DataFrame(columns=_EMPTY_COLUMNS) for freq in self.frequencys
        }
        self._symbol: Optional[str] = None

    def update(self, symbol: str, bars_by_level: Mapping[str, Iterable[Bar]]) -> None:
        self._symbol = symbol
        for level, bars in bars_by_level.items():
            self._frames[level] = bars_to_dataframe(symbol, bars)

    def klines(self, code: str, frequency: str) -> pd.DataFrame:
        return self._frames.get(frequency, pd.DataFrame(columns=_EMPTY_COLUMNS))

    @property
    def code(self) -> Optional[str]:
        return self._symbol


@dataclass
class _SymbolContext:
    code: str
    frequencys: Sequence[str]
    cl_config: Optional[dict] = None


class LegacyMarketDataBridge:
    """
    ``MarketDatas`` 替代实现，支持旧策略依赖的 `klines` 与 `get_cl_data`。
    """

    def __init__(self, market: str, symbol: str, frequencys: Sequence[str]) -> None:
        self.market = market
        self.symbol = symbol
        self.frequencys = list(frequencys)
        self._dataframes: Dict[Tuple[str, str], pd.DataFrame] = {}
        self._contexts: Dict[str, _SymbolContext] = {}
        self._cache: Dict[Tuple[str, str], ICL] = {}

    # ------------------------------------------------------------------
    # 数据写入
    # ------------------------------------------------------------------
    def set_symbol_bars(
        self,
        code: str,
        bars_by_level: Mapping[str, Iterable[Bar]],
        *,
        frequencys: Optional[Sequence[str]] = None,
    ) -> None:
        ctx = self._contexts.get(code)
        if ctx is None:
            ctx = _SymbolContext(code=code, frequencys=tuple(frequencys or self.frequencys))
            self._contexts[code] = ctx
        for level, bars in bars_by_level.items():
            df = bars_to_dataframe(code, bars)
            self._dataframes[(code, level)] = df
            self._cache.pop((code, level), None)

    # ------------------------------------------------------------------
    # Legacy API
    # ------------------------------------------------------------------
    def klines(self, code: str, frequency: str) -> pd.DataFrame:
        return self._dataframes.get((code, frequency), pd.DataFrame(columns=_EMPTY_COLUMNS))

    def get_cl_data(self, code: str, frequency: str, cl_config: Optional[dict] = None) -> ICL:
        key = (code, frequency)
        df = self.klines(code, frequency)
        if df.empty:
            raise ValueError(f"No klines available for {code} @ {frequency}")

        if key in self._cache:
            cached = self._cache[key]
            if cached.get_src_klines():
                last_cached = cached.get_src_klines()[-1].date
                if df.iloc[-1]["date"] <= last_cached:
                    return cached

        ctx = self._contexts.setdefault(code, _SymbolContext(code=code, frequencys=self.frequencys))
        if ctx.cl_config is None:
            ctx.cl_config = cl_config or query_cl_chart_config(self.market, code)

        cd = web_batch_get_cl_datas(self.market, code, {frequency: df}, ctx.cl_config)[0]
        self._cache[key] = cd
        return cd

    # ------------------------------------------------------------------
    def clear_cache(self) -> None:
        self._cache.clear()

