from chanlun_quant.ai.interface import ChanLLM, LLMClient
from chanlun_quant.ai.payload import build_ai_context
from chanlun_quant.types import PositionState, Signal, StructureState


class _Cfg:
    symbol = "SPY"
    max_leverage = 1.0
    max_position = 10_000
    max_notional = 1_000_000
    cooldown_bars = 3
    min_qty = 1
    step_qty = 1
    macd_area_mode = "hist"


def test_templates_and_llmclient_exist():
    client = LLMClient(provider="mock")
    out = client.ask_json("DECIDE_ACTION JSON")
    assert "action" in out and "quantity" in out


def test_chanllm_basic_routes():
    llm = ChanLLM(LLMClient("mock"))
    verify = llm.verify_segment_end({"seg": "S"})
    assert isinstance(verify, dict) and "segment_end" in verify

    explain = llm.explain_signal({"sig": "BUY1"})
    assert isinstance(explain, str)

    fugue = llm.assess_fugue({"levels": ["5m", "30m"], "signals": {}})
    assert isinstance(fugue, dict) and "fugue_state" in fugue

    momentum = llm.interpret_momentum({"macd": {"dif": [], "dea": [], "hist": []}})
    assert isinstance(momentum, dict) and "momentum" in momentum


def test_decide_action_with_payload():
    structure_state = StructureState(
        levels=["5m"],
        trends={},
        signals={"5m": [Signal(type="BUY1", price=1.0, index=10, level="5m")]},
        centrals={},
        relations={"score": 0.8},
    )
    position_state = PositionState(
        quantity=100,
        avg_cost=10.0,
        realized_profit=0.0,
        remaining_capital=10_000.0,
        stage="HOLDING",
    )
    cfg = _Cfg()
    context = build_ai_context(structure_state, position_state, cfg)
    assert isinstance(context, dict) and "symbol" in context

    llm = ChanLLM(LLMClient("mock"))
    result = llm.decide_action(structure_state, position_state, cfg)
    assert isinstance(result, dict)
    assert {"instruction", "valid", "errors"}.issubset(result.keys())
    assert {"action", "quantity", "reason"}.issubset(result["instruction"].keys())
