from __future__ import annotations

from typing import Iterable, List

import pandas as pd

from chanlun_quant.strategy import Action, LegacyStrategyAdapter

try:
    from chanlun.backtesting.base import Operation
except ImportError:  # pragma: no cover
    Operation = object  # type: ignore


class DummyMarketData:
    def __init__(self, closes: Iterable[float]) -> None:
        self.frequencys = ["5m"]
        self._frame = pd.DataFrame(
            {
                "close": list(closes),
            }
        )

    def klines(self, code: str, freq: str) -> pd.DataFrame:
        assert freq == self.frequencys[0]
        return self._frame


class DummyStrategy:
    def __init__(self) -> None:
        self._open_ops: List[Operation] = []
        self._close_ops: List[Operation] = []

    def enqueue_open(self, op: Operation) -> None:
        self._open_ops.append(op)

    def enqueue_close(self, op: Operation) -> None:
        self._close_ops.append(op)

    def open(self, code, market_data, poss):
        if self._open_ops:
            return self._open_ops.pop(0)
        return []

    def close(self, code, mmd, pos, market_data):
        if self._close_ops:
            return self._close_ops.pop(0)
        return []

    def is_filter_opts(self):
        return False

    def filter_opts(self, opts):
        return opts

    def clear(self):
        self._open_ops.clear()
        self._close_ops.clear()


def make_operation(opt: str, mmd: str, pos_rate: float = 1.0, msg: str = "") -> Operation:
    return Operation(code="TEST", opt=opt, mmd=mmd, pos_rate=pos_rate, msg=msg or mmd)


def test_legacy_adapter_emits_buy_signal_and_updates_position() -> None:
    strategy = DummyStrategy()
    adapter = LegacyStrategyAdapter(symbol="TEST", strategy=strategy)
    market_data = DummyMarketData([10.0, 10.5])

    buy_op = make_operation("buy", "1buy", pos_rate=0.5, msg="看涨")
    strategy.enqueue_open(buy_op)

    signal = adapter.step(market_data)
    assert signal is not None
    assert signal.signal == "BUY1"
    assert signal.suggested_action == Action.BUY_INITIAL
    assert signal.pos_rate == 0.5
    assert signal.price == 10.5

    adapter.register_fill(Action.BUY_INITIAL, quantity=100, price=signal.price, signal=signal)
    positions = adapter.positions()
    assert positions
    (_, pos) = positions.popitem()
    assert pos.amount == 100
    assert pos.price == 10.5


def test_legacy_adapter_emits_sell_all_after_buy_fill() -> None:
    strategy = DummyStrategy()
    adapter = LegacyStrategyAdapter(symbol="TEST", strategy=strategy)
    market_data = DummyMarketData([10.0, 10.0, 9.5])

    strategy.enqueue_open(make_operation("buy", "1buy"))
    signal = adapter.step(market_data)
    assert signal is not None
    adapter.register_fill(Action.BUY_INITIAL, quantity=50, price=signal.price, signal=signal)

    sell_op = make_operation("sell", "1buy", pos_rate=1.0, msg="止损")
    strategy.enqueue_close(sell_op)
    signal2 = adapter.step(market_data)
    assert signal2 is not None
    assert signal2.signal == "STOP_LOSS"
    assert signal2.suggested_action == Action.SELL_ALL

    adapter.register_fill(Action.SELL_ALL, quantity=50, price=signal2.price, signal=signal2)
    assert adapter.positions() == {}

