from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Tuple

import pytest

from chanlun_quant.integration.datafeed import LegacyDataFeed, load_legacy_bars


class FakeRow:
    def __init__(self, dt: datetime, o: float, h: float, l: float, c: float, v: float) -> None:
        self.dt = dt
        self.o = o
        self.h = h
        self.l = l
        self.c = c
        self.v = v


class FakeDB:
    def __init__(self, rows: Dict[str, Iterable[FakeRow]]) -> None:
        self.rows = rows
        self.calls: List[Tuple[str, str, str]] = []

    def klines_query(self, market, symbol, frequency, **kwargs):
        self.calls.append((market, symbol, frequency))
        return list(self.rows.get(frequency, []))


def test_load_legacy_bars_converts_rows_to_bars_sorted() -> None:
    rows = {
        "5m": [
            FakeRow(datetime(2024, 1, 1, 9, 35), 10.5, 10.7, 10.3, 10.6, 1200),
            FakeRow(datetime(2024, 1, 1, 9, 30), 10.0, 10.4, 9.8, 10.3, 1500),
        ]
    }
    db = FakeDB(rows)
    bars = load_legacy_bars(symbol="SHFE.RB", freqs=["5m"], market="futures", db=db)
    assert "5m" in bars
    extracted = bars["5m"]
    assert [bar.index for bar in extracted] == [0, 1]
    assert extracted[0].timestamp.tzinfo is not None
    assert extracted[0].open == pytest.approx(10.0)
    assert extracted[1].close == pytest.approx(10.6)
    assert db.calls == [("futures", "SHFE.RB", "5m")]


def test_legacy_datafeed_replays_loaded_bars() -> None:
    rows = {
        "5m": [
            FakeRow(datetime(2024, 1, 1, 9, 30), 10.0, 10.2, 9.8, 10.1, 1000),
            FakeRow(datetime(2024, 1, 1, 9, 35), 10.1, 10.4, 10.0, 10.3, 900),
        ],
        "30m": [
            FakeRow(datetime(2024, 1, 1, 9, 30), 10.0, 10.5, 9.7, 10.2, 5000),
            FakeRow(datetime(2024, 1, 1, 10, 0), 10.2, 10.6, 10.1, 10.5, 4800),
        ],
    }
    db = FakeDB(rows)
    feed = LegacyDataFeed(symbol="SHFE.RB", freqs=("5m", "30m"), market="futures", db=db)

    # First call returns False because HistoricalDataFeed starts with indices at -1
    assert feed.get_bars("5m") == []

    assert feed.advance() is True
    first_batch = feed.get_bars("5m")
    assert len(first_batch) == 1
    assert first_batch[0].close == pytest.approx(10.1)

    assert feed.advance() is True
    second_batch = feed.get_bars("5m")
    assert len(second_batch) == 2
    assert second_batch[-1].close == pytest.approx(10.3)

    assert feed.exhausted is True

