from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Literal, Optional, Tuple, Type, TypeVar

Level = Literal["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"]
Direction = Literal["up", "down"]
TrendState = Literal["up", "down", "range"]
Divergence = Literal["none", "trend_div", "range_div"]
Edge = Dict[str, Any]

__all__ = [
    "Level",
    "Direction",
    "TrendState",
    "Divergence",
    "Edge",
    "PenNode",
    "SegmentNode",
    "TrendNode",
    "RSG",
]

T_PenNode = TypeVar("T_PenNode", bound="PenNode")
T_SegmentNode = TypeVar("T_SegmentNode", bound="SegmentNode")
T_TrendNode = TypeVar("T_TrendNode", bound="TrendNode")
T_RSG = TypeVar("T_RSG", bound="RSG")


@dataclass
class PenNode:
    """笔节点：基于最细级别分型形成的单向走势单元。"""

    id: str
    level: Level
    i0: int
    i1: int
    high: float
    low: float
    direction: Direction
    macd_area_pos: float = 0.0
    macd_area_neg: float = 0.0
    macd_area_abs: float = 0.0
    macd_area_net: float = 0.0
    macd_peak_pos: float = 0.0
    macd_peak_neg: float = 0.0
    macd_dens: float = 0.0
    macd_eff_price: float = 0.0
    mmds: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为可 JSON 序列化的字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls: Type[T_PenNode], data: Dict[str, Any]) -> T_PenNode:
        """根据字典反序列化笔节点。"""
        return cls(**data)


@dataclass
class SegmentNode:
    """线段节点：由若干笔按特征序列唯一化组成的更高层走势单元。"""

    id: str
    level: Level
    i0: int
    i1: int
    pens: List[str]
    feature_seq: List[Literal["S", "X"]]
    trend_state: TrendState
    zhongshu: Optional[Dict[str, float]] = None
    divergence: Divergence = "none"
    macd_area_dir: float = 0.0
    macd_area_abs: float = 0.0
    macd_area_net: float = 0.0
    macd_peak_pos: float = 0.0
    macd_peak_neg: float = 0.0
    macd_dens: float = 0.0
    macd_eff_price: float = 0.0
    mmds: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为可 JSON 序列化的字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls: Type[T_SegmentNode], data: Dict[str, Any]) -> T_SegmentNode:
        """根据字典反序列化线段节点。"""
        return cls(**data)


@dataclass
class TrendNode:
    """走势段节点：由多条线段构成的高级别趋势结构。"""

    id: str
    level: Level
    segments: List[str]
    trend_type: Literal["uptrend", "downtrend", "range"]
    confirmed: bool = False
    macd_area_dir: float = 0.0
    macd_area_abs: float = 0.0
    macd_area_net: float = 0.0
    macd_peak_pos: float = 0.0
    macd_peak_neg: float = 0.0
    macd_dens: float = 0.0
    macd_eff_price: float = 0.0
    divergence: Divergence = "none"
    anchors: List[Tuple[int, float]] = field(default_factory=list)
    mmds: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为可 JSON 序列化的字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls: Type[T_TrendNode], data: Dict[str, Any]) -> T_TrendNode:
        """根据字典反序列化走势段节点。"""
        return cls(**data)


@dataclass
class RSG:
    """RSG 容器：收纳多级别笔、线段、走势段及其关系。"""

    symbol: str
    levels: List[Level]
    pens: Dict[str, PenNode] = field(default_factory=dict)
    segments: Dict[str, SegmentNode] = field(default_factory=dict)
    trends: Dict[str, TrendNode] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)
    build_info: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为完整的字典表示形式。"""
        return {
            "symbol": self.symbol,
            "levels": list(self.levels),
            "pens": {pid: pen.to_dict() for pid, pen in self.pens.items()},
            "segments": {sid: seg.to_dict() for sid, seg in self.segments.items()},
            "trends": {tid: trend.to_dict() for tid, trend in self.trends.items()},
            "edges": [dict(edge) for edge in self.edges],
            "build_info": dict(self.build_info),
        }

    def to_json(self) -> str:
        """转换为 JSON 字符串，保留中文字符。"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls: Type[T_RSG], data: Dict[str, Any]) -> T_RSG:
        """根据字典恢复 RSG 容器实例。"""
        pens = {pid: PenNode.from_dict(pdata) for pid, pdata in data.get("pens", {}).items()}
        segments = {
            sid: SegmentNode.from_dict(sdata) for sid, sdata in data.get("segments", {}).items()
        }
        trends = {
            tid: TrendNode.from_dict(tdata) for tid, tdata in data.get("trends", {}).items()
        }
        return cls(
            symbol=data["symbol"],
            levels=list(data.get("levels", [])),
            pens=pens,
            segments=segments,
            trends=trends,
            edges=[dict(edge) for edge in data.get("edges", [])],
            build_info=dict(data.get("build_info", {})),
        )

    @classmethod
    def from_json(cls: Type[T_RSG], payload: str) -> T_RSG:
        """根据 JSON 字符串恢复 RSG 容器实例。"""
        return cls.from_dict(json.loads(payload))

