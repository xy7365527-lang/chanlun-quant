from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Literal, Optional

Direction = Literal["up", "down"]
TrendType = Literal["up", "down", "flat"]
CostStageType = Literal["INITIAL", "COST_DOWN", "ZERO_COST", "NEG_COST", "WITHDRAW"]


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
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    parent_segment_id: Optional[str] = None
    parent_trend_id: Optional[str] = None
    lower_level_children: List["Stroke"] = field(default_factory=list)
    high_level_parent: Optional["Stroke"] = None
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class FeatureFractal:
    type: Literal["top", "bottom"]
    has_gap: bool
    pivot_price: float
    pivot_index: int
    strokes: List[Stroke] = field(default_factory=list)


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
    parent_segment_id: Optional[str] = None
    parent_trend_id: Optional[str] = None
    feature_sequence: List[Stroke] = field(default_factory=list)
    feature_fractal: Optional[FeatureFractal] = None
    pending_confirmation: bool = False
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class Trend:
    direction: Direction
    segments: List[Segment]
    start_index: int
    end_index: int
    level: Optional[str] = None
    id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    parent_trend_id: Optional[str] = None
    child_trend_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)


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


SignalType = Literal[
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


@dataclass
class Signal:
    type: SignalType
    price: float
    index: int
    level: Optional[str] = None
    extra: Dict[str, object] = field(default_factory=dict)
    id: Optional[str] = None
    timestamp: Optional[datetime] = None
    source: Optional[str] = None
    confidence: Optional[float] = None
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class StructureLevelState:
    level: str
    strokes: Dict[str, Stroke] = field(default_factory=dict)
    segments: Dict[str, Segment] = field(default_factory=dict)
    trends: Dict[str, Trend] = field(default_factory=dict)
    active_trend_id: Optional[str] = None
    signals: List[Signal] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class MultiLevelMapping:
    higher_level: str
    lower_level: str
    pen_map: Dict[str, List[str]] = field(default_factory=dict)
    segment_map: Dict[str, List[str]] = field(default_factory=dict)
    trend_map: Dict[str, List[str]] = field(default_factory=dict)
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class PostDivergenceOutcome:
    classification: str
    overlap_rate: float
    left_central: bool
    new_trend_direction: Optional[Direction]
    notes: str
    evidence: Dict[str, object] = field(default_factory=dict)


@dataclass
class StructureState:
    levels: List[str] = field(default_factory=list)
    level_states: Dict[str, StructureLevelState] = field(default_factory=dict)
    trends: Dict[str, Trend] = field(default_factory=dict)
    signals: Dict[str, List[Signal]] = field(default_factory=dict)
    centrals: Dict[str, Central] = field(default_factory=dict)
    relations: Dict[str, object] = field(default_factory=dict)
    multilevel_mappings: List[MultiLevelMapping] = field(default_factory=list)
    relation_matrix: Dict[str, object] = field(default_factory=dict)
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class PositionState:
    quantity: float = 0.0
    avg_cost: float = 0.0
    book_cost: float = 0.0
    realized_profit: float = 0.0
    initial_capital: float = 0.0
    remaining_capital: float = 0.0
    withdrawn_capital: float = 0.0
    initial_quantity: float = 0.0
    last_sell_qty: float = 0.0
    stage: str = "INITIAL"
    free_ride: bool = False
