from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class Position:
    qty: float
    avg_cost: float


class Reconciler:
    """Placeholder reconciler that compares ledger bucket vs broker position."""

    def diff(self, ledger_bucket: Dict[str, Any], broker_pos: Position) -> Dict[str, Any]:
        diff_qty = broker_pos.qty - float(ledger_bucket.get("qty", 0.0))
        diff_cost = broker_pos.avg_cost - float(ledger_bucket.get("avg_cost", 0.0))
        return {"qty_diff": diff_qty, "avg_cost_diff": diff_cost}
