# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd
from typing import Any


class ResampledMarketDatas:
    """
    Wrap an existing market data provider and expose 4h bars by resampling 60m data.
    """

    def __init__(self, market_datas: Any):
        self._mk = market_datas
        self.codes = getattr(market_datas, "codes", [])

    def _resample_to_4h(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        df = df.copy()
        if "datetime" in df.columns:
            idx = pd.DatetimeIndex(df["datetime"])
            df = df.rename(columns={"datetime": "datetime"})
        elif "date" in df.columns:
            idx = pd.DatetimeIndex(df["date"])
        else:
            raise ValueError("K-line dataframe must have date or datetime column for resampling.")
        df = df.set_index(idx)
        agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        out = df.resample("240min").agg(agg).dropna()
        out = out.reset_index().rename(columns={"index": "datetime"})
        return out

    def get_kline_df(self, code: str, freq: str, end_date=None):
        if freq.lower() in {"4h", "240m"}:
            base = self._mk.get_kline_df(code, "60m", end_date=end_date)
            return self._resample_to_4h(base)
        return self._mk.get_kline_df(code, freq, end_date=end_date)

    def get_cl_data(self, code: str, freq: str, end_date=None):
        if freq.lower() in {"4h", "240m"}:
            return self._mk.get_cl_data(code, "60m", end_date=end_date)
        return self._mk.get_cl_data(code, freq, end_date=end_date)
