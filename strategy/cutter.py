from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..agents.signal import Signal
from ..fugue.level_coordinator import Plan, Proposal


@dataclass
class CutterConfig:
    child_ratio_soft_cap: float = 0.33
    max_segment_share: float = 0.6


def _score(signal: Signal) -> float:
    return float(signal.weight or 0.0) * float(signal.confidence or 0.0) * float(signal.strength or 0.0)


def _band(band: Optional[List[float]]) -> Optional[List[float]]:
    if not band:
        return None
    low, high = min(band), max(band)
    if high <= low:
        return None
    return [low, high]


def signals_to_plan(
    signals: List[Signal],
    core_qty: float,
    child_max_ratio: float,
    cfg: Optional[CutterConfig] = None,
) -> Plan:
    cfg = cfg or CutterConfig()
    base_cap = max(1.0, abs(core_qty) * child_max_ratio * cfg.child_ratio_soft_cap)

    actionable = [sig for sig in signals if sig.kind in ("buy", "sell")]

    seg_signals = [
        sig for sig in actionable if any(ref.startswith("seg_") for ref in (sig.refs or []))
    ]
    pen_signals = [
        sig for sig in actionable if any(ref.startswith("pen_") for ref in (sig.refs or []))
    ]

    seg_score_sum = sum(max(_score(sig), 1e-9) for sig in seg_signals) or 1.0
    pen_score_sum = sum(max(_score(sig), 1e-9) for sig in pen_signals) or 1.0

    cap_segment = min(cfg.max_segment_share * base_cap, base_cap)
    cap_pen = base_cap - cap_segment

    proposals: List[Proposal] = []

    for sig in sorted(seg_signals, key=lambda s: (s.kind != "sell", -_score(s))):
        share = (_score(sig) / seg_score_sum) * cap_segment
        if share <= 0:
            continue
        proposals.append(
            Proposal(
                bucket="segment",
                action="SELL" if sig.kind == "sell" else "BUY",
                size_delta=share,
                price_band=_band(sig.entry_band) or _band(sig.take_band),
                why=sig.why,
                refs=sig.refs,
                methods=sig.methods,
            )
        )

    for sig in sorted(pen_signals, key=lambda s: -_score(s)):
        share = (_score(sig) / pen_score_sum) * cap_pen
        if share <= 0:
            continue
        proposals.append(
            Proposal(
                bucket="pen",
                action="SELL" if sig.kind == "sell" else "BUY",
                size_delta=share,
                price_band=_band(sig.entry_band),
                why=sig.why,
                refs=sig.refs,
                methods=sig.methods,
            )
        )

    return Plan(proposals=proposals, envelope_update=None)
