from __future__ import annotations

import argparse
import json
from typing import Sequence

from chanlun.strategy.strategy_test import StrategyTest

from chanlun_quant.integration.datafeed import load_legacy_bars
from chanlun_quant.integration.legacy_runner import MigrationSummary, run_legacy_strategy

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrated StrategyTest using chanlun-quant runtime.")
    parser.add_argument("--symbol", default="SHFE.RB", help="标的代码，例如 SHFE.RB")
    parser.add_argument("--market", default="futures", help="旧版市场代码，例如 futures/a/us")
    parser.add_argument("--freqs", default="5m", help="逗号分隔的周期列表，如 5m,30m")
    parser.add_argument("--limit", type=int, default=500, help="单周期加载的最大K线数量")
    parser.add_argument("--initial-capital", type=float, default=100_000.0, help="初始资金")
    parser.add_argument("--initial-qty", type=float, default=0.0, help="初始持仓数量（可选）")
    parser.add_argument("--partial-sell-ratio", type=float, default=0.5, help="SELL1 默认减仓比例")
    parser.add_argument("--profit-sell-ratio", type=float, default=0.3, help="PROFIT_HOLD 阶段减仓比例")
    parser.add_argument("--profit-buy-qty", type=float, default=0.0, help="利润阶段补回数量，0 表示跟随上次卖出量")
    parser.add_argument("--print-bars", action="store_true", help="调试时输出转换后的K线样本")
    return parser.parse_args()

def maybe_print_sample_bars(*, symbol: str, market: str, freqs: Sequence[str], limit: int) -> None:
    bars_by_level = load_legacy_bars(symbol=symbol, freqs=freqs, market=market, limit=limit, order="asc")
    sample = {
        level: [
            {
                "timestamp": bar.timestamp.isoformat(),
                "open": bar.open,
                "close": bar.close,
                "high": bar.high,
                "low": bar.low,
                "volume": bar.volume,
            }
            for bar in bars[:3]
        ]
        for level, bars in bars_by_level.items()
    }
    print("[DEBUG] Sample bars:", json.dumps(sample, ensure_ascii=False, indent=2))

def print_summary(migration: MigrationSummary) -> None:
    print("[StrategyTest Migration] Summary")
    print(json.dumps(migration.summary, ensure_ascii=False, indent=2))
    trades = migration.result.trades
    if trades:
        print("成交详情（前5条）:")
        for outcome in trades[:5]:
            action = outcome.action_plan.get("action")
            if hasattr(action, "value"):
                action = action.value
            print(
                json.dumps(
                    {
                        "signal": outcome.signal,
                        "action": action,
                        "quantity": outcome.action_plan.get("quantity"),
                        "price": outcome.extras.get("price"),
                        "stage": outcome.action_plan.get("stage"),
                        "next_stage": outcome.action_plan.get("next_stage"),
                    },
                    ensure_ascii=False,
                )
            )

def main() -> None:
    args = parse_args()
    freqs: Sequence[str] = tuple(freq.strip() for freq in args.freqs.split(",") if freq.strip())
    if not freqs:
        raise RuntimeError("至少需要一个周期")

    if args.print_bars:
        maybe_print_sample_bars(symbol=args.symbol, market=args.market, freqs=freqs, limit=args.limit)

    strategy = StrategyTest()
    migration = run_legacy_strategy(
        strategy=strategy,
        symbol=args.symbol,
        market=args.market,
        freqs=freqs,
        index_symbol=None,
        limit=args.limit,
        config_kwargs={
            "initial_capital": args.initial_capital,
            "initial_buy_quantity": args.initial_qty or 0.0,
            "partial_sell_ratio": args.partial_sell_ratio,
            "profit_sell_ratio": args.profit_sell_ratio,
            "profit_buy_quantity": args.profit_buy_qty,
        },
        trade_engine_kwargs={"initial_quantity": args.initial_qty},
    )
    print_summary(migration)

if __name__ == "__main__":
    main()

