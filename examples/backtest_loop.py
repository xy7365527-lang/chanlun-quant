from __future__ import annotations

import json
from dataclasses import asdict
from typing import Dict, List

from chanlun_quant.ai.interface import ChanLLM, LLMClient
from chanlun_quant.broker.interface import SimulatedBroker
from chanlun_quant.config import Config
from chanlun_quant.core.engine import ChanlunEngine
from chanlun_quant.datafeed.interface import DataFeed, ExternalDataFeedAdapter
from chanlun_quant.plugins.loader import instantiate
from chanlun_quant.types import Bar, PositionState


def _instantiate_for_backtest(cfg: Config):
    kwargs = json.loads(cfg.external_kwargs_json or "{}")
    if not cfg.external_datafeed_class:
        raise RuntimeError("CLQ_DATAFEED_CLASS 未配置；回测无法获取bars。")
    ext_feed = instantiate(cfg.external_datafeed_class, **kwargs)
    datafeed: DataFeed = ExternalDataFeedAdapter(ext_feed)

    llm = ChanLLM(client=LLMClient("mock"))
    broker = SimulatedBroker()
    return broker, llm, datafeed


def _sliding_history(series: List[Bar], window: int):
    for i in range(max(window, 50), len(series) + 1):
        yield series[:i]


def main() -> None:
    cfg = Config.from_env()
    broker, llm, feed = _instantiate_for_backtest(cfg)
    engine = ChanlunEngine(cfg=cfg, llm=llm, broker=broker)

    extra = json.loads(cfg.external_kwargs_json or "{}")
    lookback = int(extra.get("backtest_lookback", 1000))

    full_bars: Dict[str, List[Bar]] = {
        level: feed.get_bars(level, lookback=lookback) for level in cfg.levels
    }

    driver = cfg.levels[0]
    driver_series = full_bars.get(driver, [])
    if not driver_series:
        print(f"回测缺少驱动级别 {driver} 的bars")
        return

    position = PositionState(
        quantity=0,
        avg_cost=0.0,
        realized_profit=0.0,
        remaining_capital=100000.0,
        stage="INITIAL",
    )

    equity_curve = []
    for partial in _sliding_history(driver_series, window=200):
        level_bars = dict(full_bars)
        level_bars[driver] = partial
        result = engine.decide_and_execute(level_bars, position)
        instruction = result["ai"]["instruction"]
        equity_curve.append(
            {
                "idx": partial[-1].index,
                "rp": position.realized_profit,
                "qty": position.quantity,
                "avg": position.avg_cost,
                "action": instruction.get("action"),
            }
        )

    print("回测完成。最后状态：", asdict(position))
    print("equity (last 5):", equity_curve[-5:])


if __name__ == "__main__":
    main()
