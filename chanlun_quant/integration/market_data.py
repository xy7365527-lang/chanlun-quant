from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Ensure chanlun source tree is importable
_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

try:
    from chanlun import cl  # type: ignore
    from chanlun.exchange.exchange_ib import ExchangeIB  # type: ignore
except Exception as exc:  # pragma: no cover
    raise ImportError(
        "未找到 chanlun 包，请确认已安装并将 src 目录加入 PYTHONPATH。"
    ) from exc


def _parse_codes() -> List[str]:
    env_val = os.environ.get("CLQ_CODES")
    if env_val:
        codes = [code.strip() for code in env_val.split(",") if code.strip()]
    else:
        codes = ["AAPL", "MSFT", "NVDA"]
        logger.warning("CLQ_CODES 未设置，默认使用示例股票: %s", codes)
    return codes


def _parse_frequencys() -> List[str]:
    env_val = os.environ.get("CLQ_FREQUENCYS")
    if env_val:
        freqs = [freq.strip() for freq in env_val.split(",") if freq.strip()]
    else:
        freqs = ["d", "60m"]
    return freqs


def _parse_cl_config() -> Dict[str, Dict]:
    env_val = os.environ.get("CLQ_CL_CONFIG")
    if not env_val:
        return {}
    try:
        return json.loads(env_val)
    except Exception:
        logger.warning("解析 CLQ_CL_CONFIG 失败，忽略。")
        return {}


def _parse_duration_overrides() -> Dict[str, str]:
    env_val = os.environ.get("CLQ_IB_DURATION")
    if not env_val:
        return {}
    try:
        if env_val.strip().startswith("{"):
            return json.loads(env_val)
        return dict(item.split(":", 1) for item in env_val.split(","))
    except Exception:
        logger.warning("解析 CLQ_IB_DURATION 失败，忽略。")
        return {}


def _normalize_dataframe(df: pd.DataFrame, code: str) -> pd.DataFrame:
    df = df.copy()
    df = df.sort_values("date").reset_index(drop=True)
    df["code"] = code
    for col in ["open", "high", "low", "close"]:
        if col not in df.columns:
            raise ValueError(f"数据缺少必要字段 {col}")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "open", "high", "low", "close", "volume", "code"]]


@dataclass
class IBMarketDatas:
    codes: List[str]
    frequencys: List[str]
    lookback: int
    timeout: int
    duration_overrides: Dict[str, str]
    cl_config: Dict[str, Dict]

    def __post_init__(self) -> None:
        self._exchange = ExchangeIB()
        self._kline_cache: Dict[Tuple[str, str], pd.DataFrame] = {}
        self._cl_cache: Dict[Tuple[str, str, Optional[str]], cl.CL] = {}

    def _ensure_frequency_supported(self, freq: str) -> None:
        if freq not in self._exchange.support_frequencys():
            raise ValueError(f"IB 不支持频率 {freq}，可选: {list(self._exchange.support_frequencys().keys())}")

    def _fetch_klines(self, code: str, freq: str) -> pd.DataFrame:
        key = (code, freq)
        if key in self._kline_cache:
            return self._kline_cache[key]

        self._ensure_frequency_supported(freq)

        args = {"timeout": self.timeout}
        if freq in self.duration_overrides:
            args["duration"] = self.duration_overrides[freq]

        df = self._exchange.klines(code, freq, args=args)
        if df is None or df.empty:
            raise ValueError(f"从 IB 获取 {code}@{freq} 数据失败或为空。")

        df = _normalize_dataframe(df, code).tail(self.lookback)
        self._kline_cache[key] = df
        return df

    def get_kline_df(self, code: str, freq: str, end_date: Optional[str] = None) -> pd.DataFrame:
        df = self._fetch_klines(code, freq)
        if end_date:
            cutoff = pd.Timestamp(end_date)
            df = df[df["date"] <= cutoff]
        return df

    def get_cl_data(
        self,
        code: str,
        freq: str,
        end_date: Optional[str] = None,
        cl_config: Optional[Dict] = None,
    ) -> cl.CL:
        key = (code, freq, end_date)
        if key in self._cl_cache:
            return self._cl_cache[key]

        df = self.get_kline_df(code, freq, end_date=end_date)
        if df.empty:
            raise ValueError(f"{code}@{freq} 在截止 {end_date} 时没有可用于缠论的数据。")

        config = cl_config or self.cl_config.get(freq) or self.cl_config.get("default", {})
        processor = cl.CL(code, freq, config)
        cd = processor.process_klines(df)
        self._cl_cache[key] = cd
        return cd


def make_market_datas() -> IBMarketDatas:
    codes = _parse_codes()
    freqs = _parse_frequencys()
    lookback = int(os.environ.get("CLQ_LOOKBACK", "800"))
    timeout = int(os.environ.get("CLQ_IB_TIMEOUT", "60"))
    duration_overrides = _parse_duration_overrides()
    cl_cfg = _parse_cl_config()

    logger.info(
        "构建 IBMarketDatas: codes=%s, frequencys=%s, lookback=%s, timeout=%s",
        codes,
        freqs,
        lookback,
        timeout,
    )

    return IBMarketDatas(
        codes=codes,
        frequencys=freqs,
        lookback=lookback,
        timeout=timeout,
        duration_overrides=duration_overrides,
        cl_config=cl_cfg,
    )


__all__ = ["IBMarketDatas", "make_market_datas"]
