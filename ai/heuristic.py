from __future__ import annotations

from typing import Any, Dict, List

from ..config import Config
from ..core.envelope import Envelope
from ..features.segment_index import SegmentIndex
from ..fugue.level_coordinator import Plan, Proposal


class HeuristicConductor:
    """
    Fallback conductor when use_cost_zero_ai is enabled but no external LLM client is provided.
    """

    def decide(
        self,
        seg_idx: SegmentIndex,
        ledger: Dict[str, Any],
        envelope: Envelope,
        cfg: Config,
    ) -> Plan:
        pre_signals = ledger.get("_pre_signals") or []
        core_qty = float(ledger.get("core_qty", 0.0))
        cap = max(1.0, abs(core_qty) * envelope.child_max_ratio * 0.33)

        proposals: List[Proposal] = []

        for sig in pre_signals:
            if sig.get("kind") != "sell":
                continue
            refs = sig.get("refs") or []
            if not any(ref.startswith("seg_") for ref in refs):
                continue
            proposals.append(
                Proposal(
                    bucket="segment",
                    action="SELL",
                    size_delta=cap * 0.5,
                    refs=refs,
                    methods=sig.get("methods"),
                    why="heuristic: segment divergence/3rd sell",
                )
            )

        for sig in pre_signals:
            refs = sig.get("refs") or []
            if not any(ref.startswith("pen_") for ref in refs):
                continue
            kind = sig.get("kind")
            if kind not in ("buy", "sell"):
                continue
            proposals.append(
                Proposal(
                    bucket="pen",
                    action="BUY" if kind == "buy" else "SELL",
                    size_delta=cap * 0.25,
                    refs=refs,
                    methods=sig.get("methods"),
                    why="heuristic: pen T+0",
                )
            )

        return Plan(proposals=proposals, envelope_update=None)
