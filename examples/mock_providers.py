# -*- coding: utf-8 -*-
"""
Mocked providers to help wire TradingAgents selector end-to-end.
These implementations generate deterministic synthetic data so that the
wiring script can run even before real data services are connected.

Replace them with real implementations when integrating with production data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Mock market data implementation
# ---------------------------------------------------------------------------


@dataclass
class MockBI:
    direction: str
    buy_flags: Dict[str, bool]
    bc_flags: Dict[str, bool]

    def mmd_exists(self, names: List[str], _sep: str = "|") -> bool:
        return any(self.buy_flags.get(name, False) for name in names)

    def bc_exists(self, names: List[str], _sep: str = "|") -> bool:
        return any(self.bc_flags.get(name, False) for name in names)


class MockCLData:
    """
    Minimal ChanLun data stub providing the methods used by LLMMASelector.
    """

    def __init__(self, code: str, freq: str):
        self.code = code
        self.freq = freq
        self._bi = self._build_bi()

    def _build_bi(self) -> MockBI:
        # Hard-coded signals per code for demonstration purposes
        presets = {
            "MOCK1": ({"1buy": True, "2buy": False, "3buy": False}, {"pz": False, "qs": False}),
            "MOCK2": ({"1buy": False, "2buy": True, "3buy": False}, {"pz": True, "qs": False}),
            "MOCK3": ({"1buy": False, "2buy": False, "3buy": True}, {"pz": False, "qs": True}),
        }
        buys, bcs = presets.get(self.code, ({"1buy": False}, {"pz": False}))
        return MockBI(direction="up", buy_flags=buys, bc_flags=bcs)

    # --- chanlun API used by selector ------------------------------------
    def get_bis(self):
        return [self._bi]

    def get_bi_zss(self):
        # Return mock Zhongshu counts
        return [1, 2] if self.code != "MOCK3" else [1]

    def get_idx(self):
        # Provide a simple MACD snapshot
        return {
            "macd": {
                "dif": [0.6],
                "dea": [0.4],
                "hist": [0.2],
            }
        }


class MockMarketDatas:
    """
    Minimal market data provider that fabricates OHLCV series for demo usage.
    """

    def __init__(self):
        self.codes = ["MOCK1", "MOCK2", "MOCK3"]

    @staticmethod
    def _make_price_series(code: str, freq: str, periods: int, end: Optional[pd.Timestamp]) -> pd.DataFrame:
        rng = np.random.default_rng(abs(hash((code, freq))) % (2**32))
        end = end or pd.Timestamp.utcnow()

        if freq in {"d", "D"}:
            index = pd.date_range(end=end, periods=periods, freq="D")
        elif freq.endswith("m"):
            minutes = int(freq[:-1])
            index = pd.date_range(end=end, periods=periods, freq=f"{minutes}min")
        else:
            index = pd.date_range(end=end, periods=periods, freq="D")

        base = rng.uniform(20, 80)
        trend = np.linspace(0, rng.uniform(-5, 5), periods)
        noise = rng.normal(0, 1, periods).cumsum() * 0.2
        close = np.maximum(base + trend + noise, 1.0)
        high = close + rng.random(periods)
        low = close - rng.random(periods)
        open_ = close + rng.normal(0, 0.5, periods)
        volume = rng.integers(1_000, 10_000, periods)

        df = pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            },
            index=index,
        )
        df.index.name = "date"
        df.reset_index(inplace=True)
        return df

    def get_kline_df(self, code: str, freq: str, end_date: Optional[str] = None) -> pd.DataFrame:
        end = pd.Timestamp(end_date) if end_date else None
        periods = 280 if freq in {"d", "D"} else 400
        return self._make_price_series(code, freq, periods, end)

    def get_cl_data(self, code: str, freq: str, end_date: Optional[str] = None) -> MockCLData:
        return MockCLData(code=code, freq=freq)


# ---------------------------------------------------------------------------
# Factories exposed for wiring
# ---------------------------------------------------------------------------

def make_market_datas() -> MockMarketDatas:
    """
    Factory exported for CLQ_MKD_FACTORY.
    Replace this with your real market data factory once ready.
    """
    return MockMarketDatas()


def merge_candidates(market_datas: MockMarketDatas, frequencys: List[str], as_of: Optional[str] = None) -> List[str]:
    """
    Simple candidate aggregator used for demo purposes.
    """
    return market_datas.codes[:5]


def get_fundamentals(code: str) -> Dict[str, Any]:
    """
    Demo fundamentals provider that returns placeholder metrics.
    Replace with a real implementation fetching data from your DB or API.
    """
    return {
        "pe": 20.0 if code != "MOCK3" else 35.0,
        "market_cap": 5e9,
        "sector": "DemoSector",
    }
