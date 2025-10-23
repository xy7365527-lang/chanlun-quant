from __future__ import annotations

from typing import Dict, List, Tuple

from chanlun_quant.types import Signal


def _signal_to_dir(sig: Signal) -> int:
    """
    将单个信号映射到方向：
    BUY* → +1；SELL* → -1；其他/未知 → 0
    """
    sig_type = sig.type.upper()
    if sig_type.startswith("BUY"):
        return 1
    if sig_type.startswith("SELL"):
        return -1
    return 0


def _latest_dir_and_index(signals: List[Signal]) -> Tuple[int, int]:
    """
    取该级别最近一条信号的方向与索引。如空列表，返回(0, -1)。
    """
    if not signals:
        return 0, -1
    latest = signals[-1]
    return _signal_to_dir(latest), latest.index


def fuse_levels(level_signals: Dict[str, List[Signal]], disloc_window: int = 50) -> Dict[str, object]:
    """
    多级别赋格关系分析。
    """
    dir_map: Dict[str, int] = {}
    idx_map: Dict[str, int] = {}
    for level, sigs in level_signals.items():
        direction, last_index = _latest_dir_and_index(sigs)
        dir_map[level] = direction
        idx_map[level] = last_index

    directions = list(dir_map.values())
    nonzero_dirs = [d for d in directions if d != 0]

    resonance = (
        len(nonzero_dirs) == len(directions) and len(nonzero_dirs) > 0 and all(d == nonzero_dirs[0] for d in nonzero_dirs)
    )
    hedge = (1 in directions) and (-1 in directions)

    score = 0.0
    denom = sum(abs(d) for d in directions)
    if denom > 0:
        score = abs(sum(directions)) / denom

    indices = [idx for idx in idx_map.values() if idx >= 0]
    dislocation = False
    if len(indices) >= 2 and (max(indices) - min(indices)) > disloc_window:
        dislocation = True

    confidence = score * (0.0 if dislocation else 1.0)

    return {
        "resonance": resonance,
        "hedge": hedge,
        "dislocation": dislocation,
        "score": float(score),
        "confidence": float(confidence),
        "dir_map": dir_map,
        "last_idx_map": idx_map,
        # TODO: incorporate multilevel relations/nesting metrics into confidence weighting.
    }
