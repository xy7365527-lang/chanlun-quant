from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from chanlun_quant.types import Bar


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
    """Simple adapter that forwards calls to一个外部 DataFeed 实例。"""

    def __init__(self, external: object) -> None:
        self.external = external

    def advance(self) -> bool:
        if hasattr(self.external, "advance"):
            return bool(self.external.advance())
        return super().advance()

    def get_bars(self, level: str, lookback: int = 300) -> List[Bar]:
        if hasattr(self.external, "get_bars"):
            return list(self.external.get_bars(level, lookback))
        raise NotImplementedError("External datafeed缺少 get_bars(level, lookback) 接口")

    @property
    def exhausted(self) -> bool:
        if hasattr(self.external, "exhausted"):
            return bool(self.external.exhausted)
        return super().exhausted

