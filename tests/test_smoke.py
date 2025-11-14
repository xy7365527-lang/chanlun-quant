from datetime import datetime

from chanlun_quant.config import Config
from chanlun_quant.types import Bar


def test_imports_and_config():
    import chanlun_quant
    import chanlun_quant.core.kline
    import chanlun_quant.core.fractal
    import chanlun_quant.core.stroke
    import chanlun_quant.core.segment
    import chanlun_quant.core.pivot
    import chanlun_quant.core.momentum
    import chanlun_quant.core.signal
    import chanlun_quant.core.fugue
    import chanlun_quant.core.engine
    import chanlun_quant.ai.interface
    import chanlun_quant.ai.templates
    import chanlun_quant.broker.interface
    import chanlun_quant.analysis.multilevel
    import chanlun_quant.strategy.trade_rhythm

    cfg = Config()
    assert cfg.min_bars_per_pen == 5
    b = Bar(timestamp=datetime.utcnow(), open=1, high=2, low=0.5, close=1.5, volume=100, index=0, level="5m")
    assert b.close == 1.5
