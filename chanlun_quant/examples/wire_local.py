from __future__ import annotations

import json
from dataclasses import asdict

from chanlun_quant.ai.interface import ChanLLM, LLMClient
from chanlun_quant.analysis.structure import build_default_analyzer
from chanlun_quant.broker.interface import SimulatedBroker
from chanlun_quant.config import Config
from chanlun_quant.datafeed.interface import DataFeed
from chanlun_quant.integration import ExternalBundle, load_external_components
from chanlun_quant.runtime.live_loop import LiveTradingLoop
from chanlun_quant.strategy.trade_rhythm import TradeRhythmEngine


def main() -> None:
    cfg = Config.from_env()

    bundle: ExternalBundle = load_external_components(cfg)
    report = bundle.report
    print("=== External Inspection Report ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    feed: DataFeed | None = bundle.datafeed
    if feed is None:
        print("未配置或未成功加载外部数据源（CLQ_DATAFEED_CLASS），流程终止。")
        return

    broker = bundle.broker
    llm = bundle.llm if bundle.llm is not None else (ChanLLM(client=LLMClient()) if cfg.use_llm else None)

    trade_engine = TradeRhythmEngine()
    analyzer = build_default_analyzer(cfg)
    loop = LiveTradingLoop(
        config=cfg,
        datafeed=feed,
        analyzer=analyzer.analyze,
        trade_engine=trade_engine,
        broker=broker,
        llm=llm,
        sleep_fn=lambda _: None,
    )

    outcome = loop.run_step()
    print("=== Signal ===", outcome.signal)
    if outcome.decision:
        print("=== LLM Decision ===", outcome.decision.raw)
    else:
        print("=== LLM Decision === None")
    print("=== Action Plan ===", outcome.action_plan)
    print("=== Order Result ===", outcome.order_result)
    position_state = trade_engine.get_holding_manager().state
    print("=== Position State ===", asdict(position_state))


if __name__ == "__main__":
    main()

