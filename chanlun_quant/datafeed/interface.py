from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import fields
from datetime import datetime
from typing import Any, Iterable, List, Mapping, Sequence

from chanlun_quant.types import Bar

_BAR_FIELDS = {field.name for field in fields(Bar)}
_BAR_REQUIRED_KEYS = {"timestamp", "open", "high", "low", "close", "volume", "index"}

logger = logging.getLogger(__name__)


class DataFeed(ABC):
    """
    Abstract data feed interface.

    Both live trading and backtesting modules rely on this interface to request
    bars for specific levels (timeframes). Concrete implementations can expose
    additional helpers such as ``advance`` for historical replay.
    """

    @abstractmethod
    def get_bars(self, level: str, lookback: int = 300) -> List[Bar]:
        """Return the most recent bars for a specific level."""

    def advance(self) -> bool:
        """
        Optional hook for feeds that replay historical data.

        Returns True when new data becomes available. Live feeds can keep the
        default implementation and simply return True to indicate the caller
        should continue running.
        """
        return True

    @property
    def exhausted(self) -> bool:
        """
        Optional property for historical feeds.

        Should return True when no further data is available. Live feeds can
        keep the default implementation which always returns False.
        """
        return False


class ExternalDataFeedAdapter(DataFeed):
    """Adapter that wraps user-provided feeds to the ``DataFeed`` API."""

    def __init__(self, ext: Any) -> None:
        self.ext = ext

    def get_bars(self, level: str, lookback: int = 300) -> List[Bar]:
        data: Any
        if hasattr(self.ext, "get_bars"):
            data = self.ext.get_bars(level, lookback)
        elif hasattr(self.ext, "fetch"):
            try:
                data = self.ext.fetch(level=level, n=lookback)
            except TypeError:
                data = self.ext.fetch(level, lookback)
        else:
            logger.warning("external feed %s lacks get_bars/fetch methods", type(self.ext).__name__)
            return []
        return self._coerce_to_bars(data)

    def _coerce_to_bars(self, data: Any) -> List[Bar]:
        if data is None:
            return []

        if isinstance(data, Mapping):
            sequence: Sequence[Any] = [data]
        elif isinstance(data, list):
            sequence = data
        elif isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
            sequence = list(data)
        elif isinstance(data, Iterable) and not isinstance(data, (str, bytes, bytearray)):
            sequence = list(data)
        else:
            sequence = [data]

        bars: List[Bar] = []
        for item in sequence:
            try:
                bars.append(self._coerce_single(item))
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("failed to convert external bar %r: %s", item, exc)
        return bars

    def _coerce_single(self, item: Any) -> Bar:
        if isinstance(item, Bar):
            return item
        if isinstance(item, Mapping):
            payload = {key: item[key] for key in item.keys() if key in _BAR_FIELDS}
            missing = _BAR_REQUIRED_KEYS - payload.keys()
            if missing:
                raise ValueError(f"missing keys {sorted(missing)}")
            timestamp = payload.get("timestamp")
            if isinstance(timestamp, str):
                try:
                    payload["timestamp"] = datetime.fromisoformat(timestamp)
                except ValueError:
                    pass
            return Bar(**payload)
        raise TypeError(f"unsupported bar payload type: {type(item)!r}")

