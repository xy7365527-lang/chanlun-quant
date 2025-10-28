from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..agents.signal import Signal
from ..fugue.level_coordinator import Plan, Proposal


@dataclass
class CutterConfig:
    child_ratio_soft_cap: float = 0.33


def signals_to_plan(
    signals: List[Signal],
    core_qty: float,
    child_max_ratio: float,
    cfg: Optional[CutterConfig] = None,
) -> Plan:
    """将多级信号集合转化为 Proposal 计划（不考虑细节价带）。"""
    cfg = cfg or CutterConfig()
    proposals: List[Proposal] = []

    soft_cap_qty = core_qty * child_max_ratio * cfg.child_ratio_soft_cap
    cap = max(soft_cap_qty, 1.0)

    sells = [sig for sig in signals if sig.kind == "sell"]
    buys = [sig for sig in signals if sig.kind == "buy"]

    for sig in sells + buys:
        if sig.kind == "sell":
            bucket = "segment"
            size_delta = max(cap * 0.5, 1.0)
            action = "SELL"
        else:
            bucket = "pen"
            size_delta = max(cap * 0.3, 1.0)
            action = "BUY"

        proposals.append(
            Proposal(
                bucket=bucket,
                action=action,
                size_delta=float(size_delta),
                price_band=None,
                why=sig.why,
                refs=sig.refs,
            )
        )

    return Plan(proposals=proposals, envelope_update=None)

