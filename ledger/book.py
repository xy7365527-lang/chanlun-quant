from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Bucket:
    qty: float = 0.0
    avg_cost: float = 0.0
    realized_profit: float = 0.0


@dataclass
class Ledger:
    core_qty: float = 0.0
    core_avg_cost: float = 0.0
    remaining_cost: float = 0.0
    free_ride_qty: float = 0.0
    stage: str = "INITIAL"  # "INITIAL"|"REDUCING"|"PROFIT_HOLD"
    pen: Bucket = field(default_factory=Bucket)
    segment: Bucket = field(default_factory=Bucket)
    realized_total: float = 0.0
    cycles_to_free: int = 0


def apply_fill_to_bucket(
    ledger: Ledger,
    bucket: str,
    side: str,
    fill_qty: float,
    fill_price: float,
) -> None:
    """简单加权与已实现利润计算：SELL 产生的盈利优先抵扣 remaining_cost。"""
    bucket_obj = getattr(ledger, bucket)

    if side == "buy":
        new_qty = bucket_obj.qty + fill_qty
        if new_qty <= 0:
            bucket_obj.qty = 0.0
            bucket_obj.avg_cost = fill_price
        else:
            total_cost = bucket_obj.avg_cost * bucket_obj.qty + fill_price * fill_qty
            bucket_obj.avg_cost = total_cost / new_qty
            bucket_obj.qty = new_qty

    elif side == "sell":
        matched_qty = min(bucket_obj.qty, fill_qty)
        realized = (fill_price - bucket_obj.avg_cost) * matched_qty
        bucket_obj.qty = max(0.0, bucket_obj.qty - fill_qty)
        bucket_obj.realized_profit += realized
        ledger.realized_total += realized

        if realized > 0 and ledger.remaining_cost > 0:
            deduction = min(realized, ledger.remaining_cost)
            ledger.remaining_cost -= deduction

    if ledger.remaining_cost > 0:
        ledger.stage = "REDUCING"
    if ledger.remaining_cost <= 0 and ledger.free_ride_qty <= 0:
        ledger.free_ride_qty = ledger.core_qty
        ledger.stage = "PROFIT_HOLD"


def eod_flat_pen(ledger: Ledger) -> List[Dict[str, Any]]:
    """日末将 pen 桶净 0 的对冲单（占位）。返回 orders 列表。"""
    orders: List[Dict[str, Any]] = []
    qty = ledger.pen.qty
    if qty != 0:
        orders.append(
            {
                "bucket": "pen",
                "side": "sell" if qty > 0 else "buy",
                "qty": abs(qty),
                "why": "EOD pen flat",
            }
        )
    return orders
