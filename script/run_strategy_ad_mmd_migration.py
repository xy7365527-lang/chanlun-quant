from __future__ import annotations

import argparse
import json
from typing import Optional, Sequence

from chanlun.strategy.strategy_a_d_mmd_test import StrategyADMMDTest

from chanlun_quant.integration.legacy_runner import MigrationSummary, run_legacy_strategy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrated StrategyADMMDTest using chanlun-quant runtime.")
    parser.add_argument("--symbol", default="SHSE.600000", help="主交易标的代码")
    parser.add_argument("--market", default="a", help="市场代码（a/hk/us/futures 等）")
    parser.add_argument("--freqs", default="w,d", help="逗号分隔的周期列表，例如 w,d")
    parser.add_argument("--index-symbol", default="SHSE.000001", help="指数代码（用于过滤，可选）")
    parser.add_argument("--index-freqs", default=None, help="指数使用的周期（默认与主周期一致）")
    parser.add_argument("--limit", type=int, default=2000, help="每个周期加载的最大K线数量")
    parser.add_argument("--initial-capital", type=float, default=100_000.0, help="初始资金")
    parser.add_argument("--initial-qty", type=float, default=0.0, help="初始持仓数量（可选）")
    parser.add_argument("--partial-sell-ratio", type=float, default=0.5, help="SELL1 默认减仓比例")
    parser.add_argument("--profit-sell-ratio", type=float, default=0.3, help="利润阶段减仓比例")
    parser.add_argument("--profit-buy-qty", type=float, default=0.0, help="利润阶段补回数量，0 表示跟随上次卖出量")
    parser.add_argument("--filter-key", default="loss_rate", help="旧策略 filter_key 参数")
    parser.add_argument("--filter-reverse", action="store_true", help="旧策略 filter_reverse 参数（默认 False）")
    parser.add_argument("--summary-out", default=None, help="可选：将摘要写入 JSON 文件")
    return parser.parse_args()


def ensure_freqs(raw: Optional[str], fallback: Sequence[str]) -> Sequence[str]:
    if not raw:
        return tuple(fallback)
    return tuple(freq.strip() for freq in raw.split(",") if freq.strip())


def print_summary(migration: MigrationSummary) -> None:
    print("[StrategyADMMDTest Migration] Summary")
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


def maybe_export_summary(migration: MigrationSummary, path: Optional[str]) -> None:
    if not path:
        return
    output = json.dumps(migration.summary, ensure_ascii=False, indent=2)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(output)


def main() -> None:
    args = parse_args()
    freqs: Sequence[str] = tuple(freq.strip() for freq in args.freqs.split(",") if freq.strip())
    if not freqs:
        raise RuntimeError("至少需要一个周期")
    index_freqs = ensure_freqs(args.index_freqs, freqs)

    strategy = StrategyADMMDTest(
        mode="test",
        filter_key=args.filter_key,
        filter_reverse=args.filter_reverse,
    )

    migration = run_legacy_strategy(
        strategy=strategy,
        symbol=args.symbol,
        market=args.market,
        freqs=freqs,
        index_symbol=args.index_symbol,
        index_freqs=index_freqs,
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
    maybe_export_summary(migration, args.summary_out)


if __name__ == "__main__":
    main()

