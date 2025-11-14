from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from typing import Dict, List

import pandas as pd

from chanlun.base import Market
from chanlun.db import DB
from chanlun.exchange import get_exchange

FREQ_ALIAS: Dict[str, str] = {
    "1d": "1d",
    "30m": "30m",
    "15m": "15m",
    "5m": "5m",
}


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}
    required = ["code", "date", "open", "high", "low", "close", "volume"]
    for name in required:
        if name not in cols and name not in df.columns:
            raise ValueError(f"行情结果缺少 {name} 列，请检查适配器输出")
    if any(name in cols for name in required):
        df = df.rename(columns={cols.get(name, name): name for name in required})
    df = df.sort_values("date").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_and_store(symbols: List[str], freqs: List[str], days: int) -> None:
    exchange = get_exchange(Market.US)
    db = DB()
    end = datetime.utcnow()
    start = end - timedelta(days=days)

    for symbol in symbols:
        for freq in freqs:
            mapped_freq = FREQ_ALIAS.get(freq, freq)
            print(f"[{symbol}] 拉取 {freq}（适配器实际周期: {mapped_freq}）")
            df = exchange.klines(
                symbol,
                mapped_freq,
                start_date=start.strftime("%Y-%m-%d %H:%M:%S"),
                end_date=end.strftime("%Y-%m-%d %H:%M:%S"),
                args={"limit": None},
            )
            if df is None or len(df) == 0:
                print("  -> 无数据或接口返回空，请确认目标 API 是否支持该周期")
                continue
            clean = normalize_dataframe(df)
            db.klines_insert(Market.US.value, symbol, freq, clean)
            print(f"  -> 写入 {len(clean)} 条数据")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", required=True, help="逗号分隔，如 AAPL,MSFT")
    parser.add_argument("--freqs", default="1d,30m,5m")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    freqs = [f.strip() for f in args.freqs.split(",") if f.strip()]
    fetch_and_store(symbols, freqs, args.days)


if __name__ == "__main__":
    main()
