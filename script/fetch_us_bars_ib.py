from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import pandas as pd
from ib_insync import IB, Stock

from chanlun import config
from chanlun.base import Market
from chanlun.db import DB

FREQ_MAP: Dict[str, Tuple[str, str]] = {
    "1d": ("30 D", "1 day"),
    "30m": ("30 D", "30 mins"),
    "15m": ("30 D", "15 mins"),
    "5m": ("15 D", "5 mins"),
}


def fetch_ib_bars(ib: IB, symbol: str, duration: str, bar_size: str) -> pd.DataFrame:
    contract = Stock(symbol, "SMART", "USD")
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=duration,
        barSizeSetting=bar_size,
        whatToShow="TRADES",
        useRTH=False,
        formatDate=2,
    )
    if not bars:
        return pd.DataFrame()
    df = pd.DataFrame([{
        "date": b.date.astimezone(timezone.utc) if isinstance(b.date, datetime) else datetime.strptime(b.date, "%Y%m%d %H:%M:%S").replace(tzinfo=timezone.utc),
        "open": b.open,
        "high": b.high,
        "low": b.low,
        "close": b.close,
        "volume": b.volume,
    } for b in bars])
    df["code"] = symbol
    df = df.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    return df


def fetch_and_store(symbols: List[str], freqs: List[str]) -> None:
    ib = IB()
    ib.connect(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID)

    database = DB()

    try:
        for symbol in symbols:
            for freq in freqs:
                if freq not in FREQ_MAP:
                    print(f"[{symbol}] 跳过不支持的周期 {freq}")
                    continue
                duration, bar_size = FREQ_MAP[freq]
                print(f"[{symbol}] 拉取 {freq} (duration={duration}, barSize={bar_size})")
                df = fetch_ib_bars(ib, symbol, duration, bar_size)
                if df.empty:
                    print("  -> 无数据")
                    continue
                database.klines_insert(Market.US.value, symbol, freq, df)
                print(f"  -> 写入 {len(df)} 条")
    finally:
        ib.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", required=True, help="逗号分隔，如 AAPL,MSFT")
    parser.add_argument("--freqs", default="1d,30m,5m")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    freqs = [f.strip() for f in args.freqs.split(",") if f.strip()]

    fetch_and_store(symbols, freqs)


if __name__ == "__main__":
    main()
