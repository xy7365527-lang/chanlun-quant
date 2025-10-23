from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from typing import Dict, List

from chanlun_quant.ai.interface import ChanLLM, ExternalLLMClientAdapter, LLMClient
from chanlun_quant.broker.interface import ExternalBrokerAdapter, SimulatedBroker
from chanlun_quant.config import Config
from chanlun_quant.core.engine import ChanlunEngine
from chanlun_quant.datafeed.interface import DataFeed, ExternalDataFeedAdapter
from chanlun_quant.plugins.loader import instantiate
from chanlun_quant.types import Bar, PositionState


def _instantiate_external(cfg: Config):
    kwargs = json.loads(cfg.external_kwargs_json or "{}")

    if cfg.external_broker_class:
        ext_broker = instantiate(cfg.external_broker_class, **kwargs)
        broker = ExternalBrokerAdapter(ext_broker)
    else:
        broker = SimulatedBroker()

    if cfg.external_llm_client_class:
        ext_llm = instantiate(cfg.external_llm_client_class, **kwargs)
        llm = ChanLLM(client=ExternalLLMClientAdapter(ext_llm))
    else:
        llm = ChanLLM(cfg=cfg)

    if not cfg.external_datafeed_class:
        raise RuntimeError("CLQ_DATAFEED_CLASS 未配置；无法获取bars。")
    ext_feed = instantiate(cfg.external_datafeed_class, **kwargs)
    datafeed: DataFeed = ExternalDataFeedAdapter(ext_feed)

    return broker, llm, datafeed


def main() -> None:
    cfg = Config.from_env()
    broker, llm, feed = _instantiate_external(cfg)
    engine = ChanlunEngine(cfg=cfg, llm=llm, broker=broker)

    position = PositionState(
        quantity=0,
        avg_cost=0.0,
        realized_profit=0.0,
        remaining_capital=100000.0,
        stage="INITIAL",
    )

    interval_sec = int(os.environ.get("CLQ_LIVE_INTERVAL_SEC", "60"))
    print(f"[live] levels={cfg.levels}, interval={interval_sec}s")

    while True:
        level_bars: Dict[str, List[Bar]] = {
            level: feed.get_bars(level, lookback=300) for level in cfg.levels
        }

        result = engine.decide_and_execute(level_bars, position)
        instruction = result["ai"]["instruction"]
        status = result["execution"]["status"]

        print(
            f"[{instruction.get('action')}] qty={instruction.get('quantity')} "
            f"status={status} pos={asdict(position)}"
        )

        time.sleep(interval_sec)


if __name__ == "__main__":
    main()
