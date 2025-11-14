from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from ..config import Config
from ..core.engine import Engine
from ..ledger.book import Ledger


@dataclass
class StrategyConfig:
    cfg: Config


class FugueStrategy:
    """Reusable wrapper exposing the engine through a strategy-style interface."""

    def __init__(self, s_cfg: StrategyConfig):
        self.cfg = s_cfg.cfg
        self.engine = Engine(cfg=self.cfg)
        self.ledger = Ledger(core_qty=0.0, core_avg_cost=0.0, remaining_cost=0.0)

    def set_core(self, qty: float, avg_cost: float, remaining_cost: float) -> None:
        self.ledger.core_qty = qty
        self.ledger.core_avg_cost = avg_cost
        self.ledger.remaining_cost = remaining_cost

    def on_data(self, symbol: str, datafeed, last_price: float, eod: bool = False) -> List[Dict[str, Any]]:
        return self.engine.run_cycle(symbol, datafeed, last_price, self.ledger, eod=eod)

    def get_state(self) -> Dict[str, Any]:
        return {"ledger": self.ledger.__dict__.copy(), "config": self.cfg.__dict__.copy()}
