"""
使用 HistoricalDataFeed + LiveTradingLoop 演示 LLM 参与决策流程。

示例：
    python -m script.run_live_loop_llm --symbol AAPL --steps 10

该脚本会从 SQLite 数据库读取历史 K 线，构造单步 LiveTradingLoop，并在每步输出 LLM 指令与执行反馈。
如果配置了真实 LLM，会执行实际调用；否则落回 mock。
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List

from chanlun_quant.config import Config
from chanlun_quant.integration import load_external_components
from chanlun_quant.runtime.backtest import HistoricalDataFeed
from chanlun_quant.runtime.live_loop import LiveTradingLoop
from chanlun_quant.strategy.trade_rhythm import TradeRhythmEngine
from chanlun_quant.types import Bar


def _load_bars(symbol: str, freqs: List[str], lookback: int) -> Dict[str, List[Bar]]:
    db_path = Path.home() / ".chanlun_pro" / "db" / "chanlun_klines.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"未找到数据库: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    table = f"us_klines_{symbol.lower()[0]}"
    bars: Dict[str, List[Bar]] = {}
    try:
        for freq in freqs:
            cursor = conn.execute(
                f"SELECT dt, o, h, l, c, v FROM {table} WHERE f=? AND code=? ORDER BY dt DESC LIMIT ?",
                (freq, symbol, lookback),
            )
            rows = list(reversed(cursor.fetchall()))
            level_bars: List[Bar] = []
            for idx, row in enumerate(rows):
                dt = datetime.fromisoformat(row["dt"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                level_bars.append(
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
            bars[freq] = level_bars
    finally:
        conn.close()
    return bars


def main() -> None:
    parser = argparse.ArgumentParser(description="运行一次包含 LLM 的 LiveTradingLoop 演示。")
    parser.add_argument("--symbol", default="AAPL", help="标的代码")
    parser.add_argument("--freqs", default="1d,30m,5m", help="逗号分隔的周期列表")
    parser.add_argument("--steps", type=int, default=10, help="演示步数（默认 10）")
    parser.add_argument("--lookback", type=int, default=400, help="每周期加载的历史条数")
    args = parser.parse_args()

    cfg = Config.from_env()
    cfg.symbol = args.symbol
    cfg.levels = tuple(freq.strip() for freq in args.freqs.split(",") if freq.strip())
    cfg.use_llm = True

    bars_by_level = _load_bars(args.symbol, list(cfg.levels), args.lookback)
    feed = HistoricalDataFeed(bars_by_level)

    bundle = load_external_components(cfg)
    trade_engine = TradeRhythmEngine(initial_capital=cfg.initial_capital)
    loop = LiveTradingLoop(
        config=cfg,
        datafeed=feed,
        trade_engine=trade_engine,
        broker=bundle.broker,
        llm=bundle.llm,
        levels=cfg.levels,
        sleep_fn=lambda _: None,
    )

    step = 0
    print(f"[live-loop] symbol={cfg.symbol} levels={cfg.levels} steps={args.steps}")
    while step < args.steps and feed.advance():
        outcome = loop.run_step()
        decision = outcome.decision.raw if outcome.decision else {}
        order_status = outcome.order_result.status if outcome.order_result else "noop"
        print(
            f"#{step + 1} signal={outcome.signal} "
            f"action={outcome.action_plan['action']} qty={outcome.action_plan['quantity']} "
            f"llm_action={decision.get('action')} "
            f"status={order_status}"
        )
        step += 1


if __name__ == "__main__":
    main()

