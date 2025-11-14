"""
在 IB paper 账户中触发一次买入/卖出，用于验证下单链路。

示例：
    python -m script.ib_paper_trade --symbol AAPL --side buy --quantity 1
    python -m script.ib_paper_trade --symbol AAPL --side sell --quantity 1 --price 280.5
"""

from __future__ import annotations

import argparse

from chanlun import config
from chanlun_quant.broker import IBBroker


def main() -> None:
    parser = argparse.ArgumentParser(description="向 IB paper 账户发送一次测试订单。")
    parser.add_argument("--symbol", default="AAPL", help="交易标的，默认 AAPL")
    parser.add_argument("--side", choices=("buy", "sell"), required=True, help="订单方向 buy/sell")
    parser.add_argument("--quantity", type=float, required=True, help="订单数量")
    parser.add_argument("--price", type=float, help="限价；留空则发送市价单")
    parser.add_argument("--exchange", default="SMART", help="交易所代码，默认 SMART")
    parser.add_argument("--currency", default="USD", help="币种，默认 USD")
    args = parser.parse_args()

    broker = IBBroker(
        host=config.ib_host,
        port=config.ib_port,
        client_id=config.ib_client_id,
        exchange=args.exchange,
        currency=args.currency,
    )

    try:
        result = broker.place_order(
            action=args.side.upper(),
            quantity=args.quantity,
            symbol=args.symbol,
            price=args.price,
        )
        print("OrderResult:", result)
    finally:
        broker.disconnect()


if __name__ == "__main__":
    main()

