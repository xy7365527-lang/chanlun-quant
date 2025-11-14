import json

import pytest

from chanlun_quant.ai.context import (
    build_fugue_payload,
    build_momentum_payload,
    build_post_divergence_payload,
    build_segment_end_payload,
)
from chanlun_quant.ai.interface import StructureLLM
from chanlun_quant.types import FeatureFractal, Fractal, PostDivergenceOutcome, Segment, Stroke


class DummyClient:
    def __init__(self, response: dict | None = None) -> None:
        self.response = response or {"ok": True}
        self.last_prompt = None
        self.last_schema = None

    def ask_json(self, prompt: str, schema: dict | None = None) -> dict:
        self.last_prompt = prompt
        self.last_schema = schema
        json.loads(prompt.split("Input:\n", 1)[1])
        return self.response


def make_segment_with_fractal() -> Segment:
    start = Fractal(type="bottom", index=0, price=10.0, bar_index=0, level="5m")
    end = Fractal(type="top", index=5, price=15.0, bar_index=5, level="5m")
    stroke = Stroke(
        start_fractal=start,
        end_fractal=end,
        direction="up",
        high=15.0,
        low=10.0,
        start_bar_index=0,
        end_bar_index=5,
        id="0->5",
        level="5m",
    )
    segment = Segment(
        strokes=[stroke],
        direction="up",
        start_index=0,
        end_index=5,
        id="seg-1",
        level="5m",
        pens=[stroke],
    )
    segment.feature_sequence = [stroke]
    segment.feature_fractal = FeatureFractal(type="top", has_gap=False, pivot_price=15.0, pivot_index=5, strokes=[stroke])
    return segment


def test_structure_llm_invokes_client() -> None:
    client = DummyClient()
    llm = StructureLLM(client)
    context = {"foo": "bar"}
    result = llm.verify_segment_end(context)
    assert result == {"ok": True}
    assert "foo" in client.last_prompt


def test_structure_llm_requires_client() -> None:
    llm = StructureLLM()
    with pytest.raises(RuntimeError):
        llm.verify_segment_end({"a": 1})


def test_context_builders() -> None:
    segment = make_segment_with_fractal()
    payload = build_segment_end_payload(segment)
    assert payload["feature_fractal"]["type"] == "top"

    outcome = PostDivergenceOutcome(
        classification="new_trend",
        overlap_rate=0.2,
        left_central=True,
        new_trend_direction="up",
        notes="test",
        evidence={"foo": "bar"},
    )
    outcome_payload = build_post_divergence_payload(outcome)
    assert outcome_payload["classification"] == "new_trend"

    assert build_fugue_payload({"state": "共振"}) == {"state": "共振"}
    assert build_momentum_payload({"strength": 1.2}) == {"strength": 1.2}
