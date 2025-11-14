"""Strategy interfaces for cost-reduction trading."""

from .legacy_adapter import LegacyPositionBook, LegacySignal, LegacyStrategyAdapter, PriceResolver
from .position_manager import HoldingManager
from .trade_rhythm import Action, State, TradeRhythmEngine

__all__ = [
    "HoldingManager",
    "Action",
    "State",
    "TradeRhythmEngine",
    "LegacyStrategyAdapter",
    "LegacySignal",
    "LegacyPositionBook",
    "PriceResolver",
]
