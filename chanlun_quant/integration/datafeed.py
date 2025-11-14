from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

try:  # pragma: no cover - optional dependency only available with legacy codebase
    from chanlun.db import DB
except ImportError:  # pragma: no cover
    DB = None  # type: ignore

from chanlun_quant.runtime.backtest import HistoricalDataFeed
from chanlun_quant.types import Bar

__all__ = [
    "load_legacy_bars",
    "LegacyDataFeed",
]


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _row_datetime(row: Mapping[str, object] | object) -> datetime:
    if isinstance(row, Mapping):
        dt = row.get("dt")
    else:
        dt = getattr(row, "dt", None)
    if dt is None:
        raise ValueError("Legacy kline row missing datetime field 'dt'")
    return dt


def _row_to_bar(row: Mapping[str, object] | object, index: int, level: str) -> Bar:
    """
    Convert a legacy klines row to Bar.

    Supports both SQLAlchemy row objects (attribute access) and dictionary-like inputs.
    """
    if isinstance(row, Mapping):
        dt = row.get("dt")
        open_ = row.get("o") or row.get("open")
        high = row.get("h") or row.get("high")
        low = row.get("l") or row.get("low")
        close = row.get("c") or row.get("close")
        volume = row.get("v") or row.get("volume") or 0.0
    else:
        dt = getattr(row, "dt")
        open_ = getattr(row, "o", getattr(row, "open", None))
        high = getattr(row, "h", getattr(row, "high", None))
        low = getattr(row, "l", getattr(row, "low", None))
        close = getattr(row, "c", getattr(row, "close", None))
        volume = getattr(row, "v", getattr(row, "volume", 0.0))

    timestamp = _ensure_utc(dt)

    return Bar(
        timestamp=timestamp,
        open=float(open_ or 0.0),
        high=float(high or 0.0),
        low=float(low or 0.0),
        close=float(close or 0.0),
        volume=float(volume or 0.0),
        index=index,
        level=level,
    )


def load_legacy_bars(
    symbol: str,
    freqs: Sequence[str],
    market: str,
    *,
    db: Optional[object] = None,
    limit: Optional[int] = None,
    order: str = "asc",
) -> Dict[str, List[Bar]]:
    """
    Read historical bars from the legacy chanlun DB layer and convert to Bar objects.

    Parameters
    ----------
    symbol:
        Legacy instrument identifier (例如 ``SHFE.RB``).
    freqs:
        Sequence of frequencies to load, e.g. ``("5m", "30m")``.
    market:
        Legacy market code, typically来自 `chanlun.base.Market`.
    db:
        Optional DB instance. When omitted, this helper will instantiate ``chanlun.db.DB``.
    limit:
        Optional row limit per frequency. ``None`` (default) delegates to DB defaults.
    order:
        ``"asc"`` (default) returns ascending time. ``"desc"`` will be normalized to ascending.
    """
    if not freqs:
        raise ValueError("freqs cannot be empty")

    if db is None:
        if DB is None:
            raise RuntimeError("chanlun.db.DB is not available; please supply a db instance")
        db = DB()

    symbol = symbol.upper()
    market = market.lower()
    result: Dict[str, List[Bar]] = {}

    for freq in freqs:
        rows: Iterable[object] = db.klines_query(  # type: ignore[attr-defined]
            market,
            symbol,
            freq,
            limit=limit,
            order=order,
        )
        sorted_rows = sorted(rows, key=_row_datetime)
        bars = [_row_to_bar(row, idx, freq) for idx, row in enumerate(sorted_rows)]
        result[freq] = bars

    return result


class LegacyDataFeed(HistoricalDataFeed):
    """
    Convenience HistoricalDataFeed wrapper that sources bars from the legacy DB schema.

    Example
    -------
    >>> feed = LegacyDataFeed(symbol="SHFE.RB", freqs=("5m", "30m"), market="futures")
    >>> feed.advance()
    True
    >>> len(feed.get_bars("5m"))
    1
    """

    def __init__(
        self,
        symbol: str,
        freqs: Sequence[str],
        market: str,
        *,
        db: Optional[object] = None,
        limit: Optional[int] = None,
        order: str = "asc",
    ) -> None:
        bars_by_level = load_legacy_bars(
            symbol=symbol,
            freqs=freqs,
            market=market,
            db=db,
            limit=limit,
            order=order,
        )
        if not bars_by_level:
            raise ValueError(f"No bars loaded for {symbol} ({market})")
        self.symbol = symbol
        self.market = market
        self.freqs = tuple(freqs)
        self._raw = bars_by_level
        super().__init__(bars_by_level)

    @property
    def raw_bars(self) -> Mapping[str, List[Bar]]:
        """Return the immutable bars dictionary loaded from the legacy source."""
        return self._raw

