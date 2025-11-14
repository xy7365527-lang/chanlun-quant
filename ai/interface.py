from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..config import Config
from ..core.envelope import Envelope
from ..features.segment_index import SegmentIndex
from ..fugue.level_coordinator import Plan, Proposal
from .context import build_costzero_context
from .templates import COSTZERO_PROMPT, COSTZERO_SCHEMA
from .templates_full import FEWSHOTS, FUGUE_DECISION_PROMPT, FUGUE_DECISION_SCHEMA


class ChanLLM:
    """目的化执行器：唯一目标是把 remaining_cost 降到 0。"""

    def __init__(self, client: Optional[Any] = None) -> None:
        """
        client: 需实现 ask_json(prompt: str, schema: dict) -> dict
        """
        self.client = client

    def _render_prompt(self, context: Dict[str, Any]) -> str:
        context_json = json.dumps(context, ensure_ascii=False)
        return COSTZERO_PROMPT.format(context=context_json)

    def decide_costzero(
        self,
        seg_idx: SegmentIndex,
        ledger: Dict[str, Any],
        envelope: Envelope,
        cfg: Config,
    ) -> Plan:
        if not cfg.use_cost_zero_ai or self.client is None:
            raise RuntimeError("LLM not enabled")

        context = build_costzero_context(seg_idx, ledger, envelope, cfg)
        prompt = self._render_prompt(context)

        try:
            result = self.client.ask_json(prompt, schema=COSTZERO_SCHEMA)
        except Exception as exc:
            raise RuntimeError(f"LLM call failed: {exc}") from exc

        proposals: List[Proposal] = []
        for item in result.get("proposals", []):
            proposal = Proposal(
                bucket=item.get("bucket"),
                action=item.get("action"),
                size_delta=float(item.get("size_delta", 0.0)),
                price_band=item.get("price_band"),
                why=item.get("why", ""),
                refs=item.get("refs"),
            )
            if proposal.refs:
                proposal.node_id = proposal.refs[0]
            proposals.append(proposal)

        envelope_update = result.get("envelope_update")
        return Plan(proposals=proposals, envelope_update=envelope_update)

    def decide_fugue(
        self,
        seg_idx: SegmentIndex,
        ledger: Dict[str, Any],
        envelope: Envelope,
        cfg: Config,
    ) -> Plan:
        if self.client is None:
            raise RuntimeError("LLM not enabled")

        context = build_costzero_context(seg_idx, ledger, envelope, cfg)
        prompt = FUGUE_DECISION_PROMPT.format(
            fewshots=FEWSHOTS, context=json.dumps(context, ensure_ascii=False)
        )

        try:
            result = self.client.ask_json(prompt, schema=FUGUE_DECISION_SCHEMA)
        except Exception as exc:
            raise RuntimeError(f"LLM call failed: {exc}") from exc

        proposals: List[Proposal] = []
        for directive in result.get("directives", []):
            proposal = Proposal(
                bucket=directive.get("bucket"),
                action=directive.get("action"),
                size_delta=float(directive.get("size_delta", 0.0)),
                price_band=directive.get("price_band"),
                why=directive.get("narrative", ""),
                refs=directive.get("refs"),
                methods=directive.get("methods"),
            )
            if proposal.refs:
                proposal.node_id = proposal.refs[0]
            proposals.append(proposal)

        return Plan(proposals=proposals, envelope_update=None)
