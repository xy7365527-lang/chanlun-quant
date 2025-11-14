from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from chanlun_quant.types import Signal


def _signal_to_dir(sig: Signal) -> int:
    sig_type = sig.type.upper()
    if sig_type.startswith("BUY"):
        return 1
    if sig_type.startswith("SELL"):
        return -1
    return 0


@dataclass
class LevelSnapshot:
    level: str
    direction: int
    last_signal: Optional[Signal]
    last_signal_type: Optional[str]
    last_index: int
    last_price: Optional[float]
    weight: float


@dataclass
class FugueResult:
    resonance: bool
    hedge: bool
    dislocation: bool
    score: float
    confidence: float
    dominant_direction: int
    state_label: str
    commentary: str
    dir_map: Dict[str, int]
    last_idx_map: Dict[str, int]
    resonance_strength: float
    max_index_gap: int
    active_levels: int
    ordered_levels: List[str]
    level_details: List[Dict[str, object]]

    def to_dict(self) -> Dict[str, object]:
        return {
            "resonance": self.resonance,
            "hedge": self.hedge,
            "dislocation": self.dislocation,
            "score": float(self.score),
            "confidence": float(self.confidence),
            "dominant_direction": self.dominant_direction,
            "state_label": self.state_label,
            "commentary": self.commentary,
            "dir_map": dict(self.dir_map),
            "last_idx_map": dict(self.last_idx_map),
            "resonance_strength": float(self.resonance_strength),
            "max_index_gap": int(self.max_index_gap),
            "active_levels": int(self.active_levels),
            "ordered_levels": list(self.ordered_levels),
            "level_details": [dict(detail) for detail in self.level_details],
        }


class FugueAnalyzer:
    def __init__(
        self,
        level_signals: Dict[str, List[Signal]],
        *,
        disloc_window: int = 50,
        level_weights: Optional[Dict[str, float]] = None,
    ) -> None:
        self._level_signals = level_signals
        self._disloc_window = max(1, disloc_window)
        self._level_order = list(level_signals.keys())
        self._level_weights = level_weights or {}

    def analyze(self) -> FugueResult:
        snapshots = [self._build_snapshot(level, sigs) for level, sigs in self._level_signals.items()]

        positives = [snap.level for snap in snapshots if snap.direction > 0]
        negatives = [snap.level for snap in snapshots if snap.direction < 0]
        active_levels = len(positives) + len(negatives)
        resonance = active_levels > 0 and (len(positives) == active_levels or len(negatives) == active_levels)
        hedge = len(positives) > 0 and len(negatives) > 0

        weighted_sum = sum(snap.direction * snap.weight for snap in snapshots)
        total_weight = sum(snap.weight for snap in snapshots if snap.direction != 0)
        score = abs(weighted_sum) / total_weight if total_weight else 0.0
        dominant_direction = 1 if weighted_sum > 0 else -1 if weighted_sum < 0 else 0

        indices = [snap.last_index for snap in snapshots if snap.last_index >= 0]
        max_index_gap = (max(indices) - min(indices)) if len(indices) >= 2 else 0
        dislocation = max_index_gap > self._disloc_window if len(indices) >= 2 else False

        penalty = 0.0
        if dislocation:
            penalty += min(1.0, max_index_gap / self._disloc_window)
        if hedge:
            penalty += 0.3
        confidence = max(0.0, (1.0 - penalty) * score)

        state_label = self._compose_state_label(resonance, hedge, dominant_direction)
        commentary = self._compose_commentary(resonance, hedge, dominant_direction, positives, negatives, max_index_gap)

        dir_map = {snap.level: snap.direction for snap in snapshots}
        last_idx_map = {snap.level: snap.last_index for snap in snapshots}
        level_details = [self._snapshot_detail(snap) for snap in snapshots]

        return FugueResult(
            resonance=resonance,
            hedge=hedge,
            dislocation=dislocation,
            score=score,
            confidence=confidence,
            dominant_direction=dominant_direction,
            state_label=state_label,
            commentary=commentary,
            dir_map=dir_map,
            last_idx_map=last_idx_map,
            resonance_strength=score,
            max_index_gap=max_index_gap,
            active_levels=active_levels,
            ordered_levels=self._level_order,
            level_details=level_details,
        )

    def _build_snapshot(self, level: str, signals: List[Signal]) -> LevelSnapshot:
        weight = float(self._level_weights.get(level, 1.0))
        if signals:
            last = signals[-1]
            direction = _signal_to_dir(last)
            last_signal_type = last.type
            last_index = int(last.index)
            last_price = float(last.price)
        else:
            last = None
            direction = 0
            last_signal_type = None
            last_index = -1
            last_price = None
        return LevelSnapshot(
            level=level,
            direction=direction,
            last_signal=last,
            last_signal_type=last_signal_type,
            last_index=last_index,
            last_price=last_price,
            weight=weight,
        )

    @staticmethod
    def _compose_state_label(resonance: bool, hedge: bool, dominant_direction: int) -> str:
        if resonance:
            if dominant_direction > 0:
                return "共振上行"
            if dominant_direction < 0:
                return "共振下行"
            return "同步震荡"
        if hedge:
            return "级别对冲"
        if dominant_direction > 0:
            return "多头占优"
        if dominant_direction < 0:
            return "空头占优"
        return "方向不明"

    def _compose_commentary(
        self,
        resonance: bool,
        hedge: bool,
        dominant_direction: int,
        positives: List[str],
        negatives: List[str],
        max_index_gap: int,
    ) -> str:
        commentary: List[str] = []
        if resonance:
            if dominant_direction > 0:
                commentary.append(f"多头共振：{', '.join(positives)}")
            elif dominant_direction < 0:
                commentary.append(f"空头共振：{', '.join(negatives)}")
            else:
                commentary.append("各级别同步但方向暂无定论")
        elif hedge:
            commentary.append(
                f"存在对冲：多头({', '.join(positives) or '无'}) vs 空头({', '.join(negatives) or '无'})"
            )
        elif dominant_direction > 0 and positives:
            commentary.append(f"多头占优：{', '.join(positives)}")
        elif dominant_direction < 0 and negatives:
            commentary.append(f"空头占优：{', '.join(negatives)}")
        else:
            commentary.append("当前缺乏明显主导级别")

        if max_index_gap > 0:
            commentary.append(f"最大信号间隔 {max_index_gap}")
        return "；".join(commentary)

    @staticmethod
    def _snapshot_detail(snapshot: LevelSnapshot) -> Dict[str, object]:
        if snapshot.direction > 0:
            label = "多头"
        elif snapshot.direction < 0:
            label = "空头"
        else:
            label = "观望"
        return {
            "level": snapshot.level,
            "direction": snapshot.direction,
            "label": label,
            "last_signal": snapshot.last_signal_type,
            "last_index": snapshot.last_index,
            "last_price": snapshot.last_price,
            "weight": snapshot.weight,
        }


def fuse_levels(
    level_signals: Dict[str, List[Signal]],
    disloc_window: int = 50,
    *,
    level_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, object]:
    analyzer = FugueAnalyzer(level_signals, disloc_window=disloc_window, level_weights=level_weights)
    return analyzer.analyze().to_dict()
