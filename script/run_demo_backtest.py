"""
统一入口：加载 SQLite 中的多周期 K 线并运行 BacktestRunner。

用法：
    python -m script.run_demo_backtest --symbol AAPL --steps 500
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from chanlun_quant.broker.interface import SimulatedBroker
from chanlun_quant.config import Config
from chanlun_quant.runtime.backtest import BacktestRunner
from chanlun_quant.strategy.trade_rhythm import TradeRhythmEngine
from chanlun_quant.types import Bar


def load_bars(symbol: str, freqs: List[str], lookback: int) -> Dict[str, List[Bar]]:
    db_path = Path.home() / ".chanlun_pro" / "db" / "chanlun_klines.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"未找到数据库: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    table = f"us_klines_{symbol.lower()[0]}"
    bars_by_level: Dict[str, List[Bar]] = {}
    try:
        for freq in freqs:
            cursor = conn.execute(
                f"SELECT dt, o, h, l, c, v FROM {table} WHERE f=? AND code=? ORDER BY dt DESC LIMIT ?",
                (freq, symbol, lookback),
            )
            rows = list(reversed(cursor.fetchall()))
            series: List[Bar] = []
            for idx, row in enumerate(rows):
                dt = datetime.fromisoformat(row["dt"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                series.append(
                    Bar(
                        timestamp=dt,
                        open=row["o"],
                        high=row["h"],
                        low=row["l"],
                        close=row["c"],
                        volume=row["v"],
                        index=idx,
                        level=freq,
                    )
                )
            bars_by_level[freq] = series
    finally:
        conn.close()
    return bars_by_level


def main() -> None:
    parser = argparse.ArgumentParser(description="运行一个最小回测 Demo。")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--freqs", default="1d,30m,5m")
    parser.add_argument("--lookback", type=int, default=500)
    args = parser.parse_args()

    freqs = [f.strip() for f in args.freqs.split(",") if f.strip()]
    bars_by_level = load_bars(args.symbol, freqs, args.lookback)

    cfg = Config(
        symbol=args.symbol,
        levels=tuple(freqs),
        initial_buy_quantity=100.0,
        partial_sell_ratio=0.5,
        profit_sell_ratio=0.3,
        initial_capital=100_000.0,
        use_llm=False,
    )

    trade_engine = TradeRhythmEngine(initial_capital=cfg.initial_capital)
    broker = SimulatedBroker(initial_cash=cfg.initial_capital)
    runner = BacktestRunner(
        config=cfg,
        bars_by_level=bars_by_level,
        trade_engine=trade_engine,
        broker=broker,
    )
    result = runner.run()

    state = trade_engine.get_holding_manager().state
    print(f"总步数: {len(result.outcomes)}")
    print(f"成交次数: {len(result.trades)}")
    print(f"最终阶段: {state.stage}")
    print(f"最终仓位: {state.quantity}")
    print(f"已实现收益: {state.realized_profit}")


if __name__ == "__main__":
    main()

