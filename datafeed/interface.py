from __future__ import annotations

from typing import Any, List

from chanlun_quant.types import Bar


class DataFeed:
    """Abstract data feed interface for retrieving bar data."""

    def get_bars(self, level: str, lookback: int = 300) -> List[Bar]:
        raise NotImplementedError


class ExternalDataFeedAdapter(DataFeed):
    """Wraps an external feed implementation with a minimal adapter."""

    def __init__(self, ext: Any) -> None:
        self.ext = ext

    def get_bars(self, level: str, lookback: int = 300) -> List[Bar]:
        if hasattr(self.ext, "get_bars"):
            return self.ext.get_bars(level, lookback)
        if hasattr(self.ext, "fetch"):
            return self.ext.fetch(level=level, n=lookback)
        return []
