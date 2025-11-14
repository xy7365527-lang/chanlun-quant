from __future__ import annotations

import json
import os
import time
from typing import Dict, List

from ..config import Config
from ..core.backtest import BacktestBroker
from ..core.engine import Engine
from ..ledger.book import Ledger


class ArrayFeed:
    """简单数组回放，逐步扩展窗口供 Engine 读取。"""

    def __init__(self, data: Dict[str, Dict[str, List[float]]], window: int = 120) -> None:
        self.data = data
        self.window = window
        self.cursor = window

    def step(self) -> bool:
        self.cursor += 1
        any_len = len(next(iter(self.data.values()))["close"])
        return self.cursor <= any_len

    def get_bars(self, symbol: str, level: str) -> Dict[str, List[float]]:
        raw = self.data[level]
        return {key: values[: self.cursor] for key, values in raw.items()}

    def last_price(self, level: str = "M15") -> float:
        return self.data[level]["close"][self.cursor - 1]


def run_simple(symbol: str, arrays: Dict[str, Dict[str, List[float]]], out_dir: str = "runs") -> str:
    os.makedirs(out_dir, exist_ok=True)
    cfg = Config(use_rsg=True, use_auto_levels=False, use_cost_zero_ai=False, child_max_ratio=0.35)
    broker = BacktestBroker(fee_bps=4.0, slippage_bps=3.0)
    engine = Engine(cfg=cfg, broker=broker)
    ledger = Ledger(core_qty=1000.0, core_avg_cost=100.0, remaining_cost=5000.0)

    feed = ArrayFeed(arrays, window=120)
    output_path = os.path.join(out_dir, f"{symbol}_{int(time.time())}.jsonl")
    with open(output_path, "w", encoding="utf-8") as fh:
        while feed.step():
            last_price = feed.last_price("M15")
            orders = engine.run_cycle(symbol, feed, last_price=last_price, ledger=ledger, eod=False)
            record = {
                "cursor": feed.cursor,
                "orders": orders,
                "remaining_cost": ledger.remaining_cost,
                "stage": ledger.stage,
                "realized_total": ledger.realized_total,
                "pen_qty": ledger.pen.qty,
                "segment_qty": ledger.segment.qty,
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return output_path

