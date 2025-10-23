from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, List

Direction = Literal["up", "down"]
TrendType = Literal["up", "down", "flat"]


@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    index: int
    level: Optional[str] = None


@dataclass
class Fractal:
    type: Literal["top", "bottom"]
    index: int
    price: float
    bar_index: int
    level: Optional[str] = None


@dataclass
class Stroke:
    start_fractal: Fractal
    end_fractal: Fractal
    direction: Direction
    high: float
    low: float
    start_bar_index: int
    end_bar_index: int
    id: Optional[str] = None
    level: Optional[str] = None
    lower_level_children: List["Stroke"] = field(default_factory=list)
    high_level_parent: Optional["Stroke"] = None


@dataclass
class Segment:
    strokes: List[Stroke]
    direction: Direction
    start_index: int
    end_index: int
    end_confirmed: bool = True
    id: Optional[str] = None
    level: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    pens: List[Stroke] = field(default_factory=list)
    child_segments: List["Segment"] = field(default_factory=list)
    parent_segment: Optional["Segment"] = None


@dataclass
class Trend:
    direction: Direction
    segments: List[Segment]
    start_index: int
    end_index: int
    level: Optional[str] = None


@dataclass
class Central:
    level: str
    zg: float
    zd: float
    start_index: int
    end_index: int
    stroke_indices: List[int] = field(default_factory=list)
    extended: bool = False
    expanded: bool = False
    newborn: bool = False


@dataclass
class Divergence:
    level: str
    kind: Literal["trend", "range"]
    start_index: int
    end_index: int
    area_a: float
    area_c: float
    is_divergent: bool


@dataclass
class Signal:
    type: Literal[
        "BUY1",
        "BUY2",
        "BUY3",
        "SELL1",
        "SELL2",
        "SELL3",
        "BUY2_LIKE",
        "BUY3_LIKE",
        "SELL2_LIKE",
        "SELL3_LIKE",
    ]
    price: float
    index: int
    level: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class PositionState:
    quantity: int = 0
    avg_cost: float = 0.0
    realized_profit: float = 0.0
    remaining_capital: float = 0.0
    stage: str = "INITIAL"


@dataclass
class StructureState:
    levels: List[str] = field(default_factory=list)
    trends: dict = field(default_factory=dict)
    signals: dict = field(default_factory=dict)
    centrals: dict = field(default_factory=dict)
    relations: dict = field(default_factory=dict)
