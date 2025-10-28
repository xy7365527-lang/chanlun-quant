from __future__ import annotations

import csv
import itertools
import os
from typing import Dict, Iterable, List

from ..config import Config
from ..core.backtest import BacktestBroker
from ..core.engine import Engine
from ..ledger.book import Ledger


class ArrayFeed:
    def __init__(self, data: Dict[str, Dict[str, List[float]]], window: int = 120) -> None:
        self.data = data
        self.window = window
        self.cursor = window

    def step(self) -> bool:
        self.cursor += 1
        any_len = len(next(iter(self.data.values()))["close"])
        return self.cursor <= any_len

    def get_bars(self, symbol: str, level: str) -> Dict[str, List[float]]:
        series = self.data[level]

        def take(arr: List[float]) -> List[float]:
            return arr[: self.cursor]

        return {key: take(values) for key, values in series.items()}

    def last_price(self, level: str = "M15") -> float:
        return self.data[level]["close"][self.cursor - 1]


def run_grid(
    symbol: str,
    arrays: Dict[str, Dict[str, List[float]]],
    switches: Dict[str, Iterable],
    out_csv: str = "runs/ab_grid.csv",
) -> str:
    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    keys = list(switches.keys())
    rows: List[Dict[str, float]] = []

    for values in itertools.product(*switches.values()):
        params = dict(zip(keys, values))
        cfg = Config(
            use_rsg=True,
            use_auto_levels=False,
            use_cost_zero_ai=params.get("use_ai", False),
            k_grid=params.get("k_grid", 0.25),
            child_max_ratio=params.get("child_ratio", 0.35),
            fee_bps=params.get("fee_bps", 4.0),
            slippage_bps=params.get("slippage_bps", 3.0),
        )
        broker = BacktestBroker(cfg.fee_bps, cfg.slippage_bps)
        engine = Engine(cfg=cfg, broker=broker)
        ledger = Ledger(core_qty=1000, core_avg_cost=100.0, remaining_cost=5000.0)

        feed = ArrayFeed(arrays, window=120)
        while feed.step():
            last_price = feed.last_price("M15")
            engine.run_cycle(symbol, feed, last_price=last_price, ledger=ledger, eod=False)

        rows.append(
            {
                **params,
                "last_remaining_cost": ledger.remaining_cost,
                "realized_total": ledger.realized_total,
            }
        )

    with open(out_csv, "w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return out_csv
