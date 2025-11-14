from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import yaml

from chanlun_quant.integration.legacy_runner import MigrationSummary, ensure_index_freqs, load_strategy, run_legacy_strategy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="通用 Legacy 策略迁移执行器")
    parser.add_argument("--strategy", help="策略路径 module:Class，例如 chanlun.strategy.strategy_test:StrategyTest")
    parser.add_argument("--symbol", help="主交易标的代码")
    parser.add_argument("--market", default="a", help="市场代码（a/hk/us/futures 等）")
    parser.add_argument("--freqs", required=True, help="逗号分隔的周期列表，例如 w,d")
    parser.add_argument("--index-symbol", default=None, help="指数代码，可选")
    parser.add_argument("--index-freqs", default=None, help="指数周期，默认与主周期一致")
    parser.add_argument("--strategy-kwargs", default=None, help="策略构造参数 JSON 字符串，可选")
    parser.add_argument("--config", default=None, help="配置文件（YAML），可通过 --case 读取")
    parser.add_argument("--case", default=None, help="配置文件中的 case 名称")
    parser.add_argument("--limit", type=int, default=None, help="单周期最大 K 线数量")
    parser.add_argument("--initial-capital", type=float, default=100_000.0, help="初始资金")
    parser.add_argument("--initial-qty", type=float, default=0.0, help="初始持仓数量")
    parser.add_argument("--partial-sell-ratio", type=float, default=0.5, help="SELL1 默认减仓比例")
    parser.add_argument("--profit-sell-ratio", type=float, default=0.3, help="利润阶段减仓比例")
    parser.add_argument("--profit-buy-qty", type=float, default=0.0, help="利润阶段补回数量")
    parser.add_argument("--summary-out", default=None, help="将摘要写入 JSON 文件")
    return parser.parse_args()


def load_case_config(path: Optional[Path], case: Optional[str]) -> Dict[str, Any]:
    if not path or not case:
        return {}
    if not path.exists():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for item in data.get("strategies", []):
        if item.get("name") == case:
            return item
    raise RuntimeError(f"case '{case}' not found in {path}")


def merge_args_with_case(args: argparse.Namespace, case_cfg: Dict[str, Any]) -> argparse.Namespace:
    for key, value in case_cfg.items():
        if key in {"name", "status", "notes"}:
            continue
        if getattr(args, key, None) in {None, "", False}:
            setattr(args, key, value)
    return args


def stringify_summary(migration: MigrationSummary) -> str:
    return json.dumps(migration.summary, ensure_ascii=False, indent=2)


def main() -> None:
    args = parse_args()

    case_cfg = load_case_config(Path(args.config)) if args.config else {}
    if args.case:
        case = load_case_config(Path(args.config), args.case)
        args = merge_args_with_case(args, case)

    freqs: Sequence[str] = tuple(freq.strip() for freq in args.freqs.split(",") if freq.strip())
    if not freqs:
        raise RuntimeError("至少需要一个周期")
    index_freqs = ensure_index_freqs(
        tuple(freq.strip() for freq in args.index_freqs.split(",") if args.index_freqs and freq.strip())
        if args.index_freqs
        else None,
        freqs,
    )

    strategy_kwargs = json.loads(args.strategy_kwargs) if args.strategy_kwargs else None
    strategy = load_strategy(args.strategy, strategy_kwargs)

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

    print("[Legacy Strategy Migration] Summary")
    print(stringify_summary(migration))
    if migration.result.trades:
        print("成交详情（前5条）:")
        for outcome in migration.result.trades[:5]:
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

    if args.summary_out:
        Path(args.summary_out).write_text(stringify_summary(migration), encoding="utf-8")


if __name__ == "__main__":
    main()
