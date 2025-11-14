import os
from contextlib import contextmanager

from chanlun_quant.ai.interface import ChanLLM, LLMClient
from chanlun_quant.config import Config
from chanlun_quant.types import PositionState, StructureState


@contextmanager
def _temp_env(overrides):
    original = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_llmclient_provider_fallback_to_mock():
    client = LLMClient(provider="deepseek", api_base="", api_key="", model="")
    out = client.ask_json("DECIDE_ACTION JSON")
    assert "action" in out and "quantity" in out


def test_chanllm_from_cfg_uses_provider():
    overrides = {
        "CLQ_LLM_PROVIDER": "mock",
        "CLQ_LLM_API_BASE": "",
        "CLQ_LLM_API_KEY": "",
        "CLQ_LLM_MODEL": "",
    }
    with _temp_env(overrides):
        cfg = Config.from_env()
        llm = ChanLLM(cfg=cfg)

        structure = StructureState(
            levels=["5m"],
            trends={},
            signals={},
            centrals={},
            relations={},
        )
        position = PositionState(
            quantity=0,
            avg_cost=0.0,
            realized_profit=0.0,
            remaining_capital=0.0,
            stage="INITIAL",
        )

        result = llm.decide_action(structure, position, cfg)
        assert "instruction" in result
        assert "valid" in result
