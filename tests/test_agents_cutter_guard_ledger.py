from chanlun_quant.config import Config
from chanlun_quant.core.engine import Engine
from chanlun_quant.ledger.book import Ledger


class DummyFeed:
    def get_bars(self, symbol, level):
        n = 120
        close = [i * 0.1 for i in range(n)]
        high = [c + 0.05 for c in close]
        low = [c - 0.05 for c in close]
        macd = [((i % 10) - 5) / 10 for i in range(n)]
        return {"close": close, "high": high, "low": low, "macd": macd}


def test_full_loop_without_llm() -> None:
    engine = Engine(cfg=Config(use_rsg=True, use_auto_levels=False, use_cost_zero_ai=False))
    ledger = Ledger(core_qty=1000.0, core_avg_cost=100.0, remaining_cost=5000.0)
    orders = engine.run_cycle("X", DummyFeed(), last_price=12.3, ledger=ledger, eod=True)
    assert isinstance(orders, list)
    assert ledger.remaining_cost <= 5000.0

