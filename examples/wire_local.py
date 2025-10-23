from __future__ import annotations

import json
from dataclasses import asdict

from chanlun_quant.ai.interface import ChanLLM, ExternalLLMClientAdapter, LLMClient
from chanlun_quant.broker.interface import ExternalBrokerAdapter, SimulatedBroker
from chanlun_quant.config import Config
from chanlun_quant.core.engine import ChanlunEngine
from chanlun_quant.datafeed.interface import DataFeed, ExternalDataFeedAdapter
from chanlun_quant.integration.inspector import inspect_external
from chanlun_quant.plugins.loader import instantiate
from chanlun_quant.types import PositionState


def _load_external(path: str, cfg: Config):
    if not path:
        return None
    payload = (cfg.external_kwargs_json or "").strip()
    kwargs = {}
    if payload:
        try:
            kwargs = json.loads(payload)
        except Exception:
            kwargs = {}
    return instantiate(path, **kwargs)


def main() -> None:
    cfg = Config.from_env()
    report = inspect_external(cfg)
    print("=== External Inspection Report ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    broker_obj = _load_external(cfg.external_broker_class, cfg)
    broker = ExternalBrokerAdapter(broker_obj) if broker_obj else SimulatedBroker()

    if cfg.external_llm_client_class:
        llm_obj = _load_external(cfg.external_llm_client_class, cfg)
        llm = ChanLLM(client=ExternalLLMClientAdapter(llm_obj)) if llm_obj else ChanLLM(client=LLMClient("mock"))
    else:
        llm = ChanLLM(cfg=cfg)

    datafeed_obj = _load_external(cfg.external_datafeed_class, cfg)
    if not datafeed_obj:
        print("External datafeed not configured or failed to load (CLQ_DATAFEED_CLASS).")
        return
    feed: DataFeed = ExternalDataFeedAdapter(datafeed_obj)

    level_bars = {level: feed.get_bars(level, lookback=300) for level in cfg.levels}
    level_bars = {level: bars for level, bars in level_bars.items() if bars}
    if not level_bars:
        print("No bars retrieved from external datafeed.")
        return

    engine = ChanlunEngine(cfg=cfg, llm=llm, broker=broker)
    position = PositionState(
        quantity=0,
        avg_cost=0.0,
        realized_profit=0.0,
        remaining_capital=100000.0,
        stage="INITIAL",
    )
    result = engine.decide_and_execute(level_bars, position)

    print("=== AI Instruction ===")
    print(json.dumps(result["ai"]["instruction"], ensure_ascii=False, indent=2))
    print("=== Execution ===")
    print(json.dumps(result["execution"], ensure_ascii=False, indent=2))
    print("=== Position ===")
    print(json.dumps(asdict(position), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
