"""
订阅 IB 实时行情的示例脚本。

用法：
    python -m script.ib_stream_demo --symbol AAPL --seconds 30

脚本会连接到 config.py 中配置的 IB 主机，订阅指定合约的实时行情，
在给定的时间范围内打印最新成交价、买卖价与成交量。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from typing import Optional

from ib_insync import IB, Stock, Ticker

from chanlun import config


def _format_price(value: Optional[float]) -> str:
    return f"{value:.4f}" if value is not None else "-"


def stream_market_data(symbol: str, exchange: str, currency: str, seconds: int, snapshot: bool) -> None:
    ib = IB()
    ib.connect(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID)

    contract = Stock(symbol, exchange, currency)
    ticker: Ticker = ib.reqMktData(contract, "", snapshot, False)

    deadline = datetime.now(tz=timezone.utc) + timedelta(seconds=seconds)
    last_printed: Optional[datetime] = None

    try:
        while datetime.now(tz=timezone.utc) < deadline:
            ib.waitOnUpdate(timeout=1)
            ts = ticker.time or datetime.now(tz=timezone.utc)
            if last_printed and ts <= last_printed:
                continue

            last_printed = ts
            print(
                f"[{ts.astimezone().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"last={_format_price(ticker.last)} "
                f"bid={_format_price(ticker.bid)} "
                f"ask={_format_price(ticker.ask)} "
                f"volume={ticker.volume or '-'}"
            )
            if snapshot:
                break
    finally:
        ib.cancelMktData(contract)
        ib.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="订阅 IB 实时行情，便于检查 API 连接是否稳定。")
    parser.add_argument("--symbol", default="AAPL", help="合约代码，默认 AAPL")
    parser.add_argument("--exchange", default="SMART", help="交易所，默认 SMART")
    parser.add_argument("--currency", default="USD", help="货币，默认 USD")
    parser.add_argument("--seconds", type=int, default=30, help="订阅持续的秒数，默认 30 秒")
    parser.add_argument("--snapshot", action="store_true", help="是否只请求一次快照")
    args = parser.parse_args()

    stream_market_data(
        symbol=args.symbol,
        exchange=args.exchange,
        currency=args.currency,
        seconds=max(1, args.seconds),
        snapshot=args.snapshot,
    )


if __name__ == "__main__":
    main()

