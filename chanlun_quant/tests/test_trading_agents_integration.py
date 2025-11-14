from __future__ import annotations

from datetime import datetime, timedelta

from chanlun_quant.ai.trading_agents import ResearchItem, TradingAgentsManager, build_ta_prompt, get_ta_schema


class DummyCfg:
    ta_enabled = True
    ta_score_threshold = 0.5
    ta_gate_mode = "soft"
    ta_cache_minutes = 1.0
    ta_adapter_class = ""
    ta_kwargs_json = ""
    ta_skip_on_fail = True


def test_research_item_from_dict_handles_defaults() -> None:
    item = ResearchItem.from_dict({"ta_score": 0.8, "ta_recommendation": "buy"}, symbol_fallback="BTCUSDT")
    assert item.symbol == "BTCUSDT"
    assert item.score == 0.8
    assert item.recommendation == "buy"
    assert item.ta_gate is True


def test_trading_agents_manager_returns_default_packet() -> None:
    manager = TradingAgentsManager(DummyCfg())
    packet, item = manager.get_research("ETHUSDT", {"structure": {}}, "INITIAL")
    assert packet is not None
    assert item is not None
    assert packet.analysis
    assert packet.analysis[0].symbol == "ETHUSDT"
    assert item.symbol == "ETHUSDT"

    cached_packet, cached_item = manager.get_research("ETHUSDT", {"structure": {}}, "INITIAL")
    assert cached_packet is packet
    assert cached_item is item


def test_prompt_building_uses_schema() -> None:
    prompt = build_ta_prompt({"foo": "bar"})
    schema = get_ta_schema()
    assert "foo" in prompt
    assert schema.strip() in prompt

