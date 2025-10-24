from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

DEFAULT_PERIODS = [5, 13, 21, 34, 55, 89, 144, 233]


@dataclass
class MAState:
    bull_alignment: bool
    bear_alignment: bool
    glue: bool
    diverge_up: bool
    diverge_down: bool
    resist_levels: List[int]
    support_levels: List[int]
    strength_category: int
    snapshot: Dict[int, float]


def _calc_ma(df: pd.DataFrame, periods: List[int]) -> Dict[int, pd.Series]:
    return {p: df["close"].rolling(p, min_periods=p).mean() for p in periods}


def _alignment(vals: Dict[int, float]) -> Tuple[bool, bool]:
    ks = sorted(vals.keys())
    arr = [vals[k] for k in ks]
    bull = all(arr[i] > arr[i + 1] for i in range(len(arr) - 1))
    bear = all(arr[i] < arr[i + 1] for i in range(len(arr) - 1))
    return bull, bear


def _glue(vals: Dict[int, float], close: float, eps_ratio: float = 0.005) -> bool:
    v = list(vals.values())
    if any(np.isnan(vv) for vv in v):
        return False
    rng = max(v) - min(v)
    return (rng / close) < eps_ratio


def _diverge(prev_vals: Dict[int, float], vals: Dict[int, float]) -> Tuple[bool, bool]:
    ks = sorted(vals.keys())
    need = [ks[0], ks[1], ks[2]]
    if any(np.isnan(prev_vals[k]) or np.isnan(vals[k]) for k in need):
        return False, False
    cond_up_order = vals[ks[0]] > vals[ks[1]] > vals[ks[2]]
    cond_dn_order = vals[ks[0]] < vals[ks[1]] < vals[ks[2]]
    up_spread = (
        (vals[ks[0]] - vals[ks[1]]) > (prev_vals[ks[0]] - prev_vals[ks[1]])
        and (vals[ks[1]] - vals[ks[2]]) > (prev_vals[ks[1]] - prev_vals[ks[2]])
    )
    dn_spread = (
        (vals[ks[1]] - vals[ks[0]]) > (prev_vals[ks[1]] - prev_vals[ks[0]])
        and (vals[ks[2]] - vals[ks[1]]) > (prev_vals[ks[2]] - prev_vals[ks[1]])
    )
    return cond_up_order and up_spread, cond_dn_order and dn_spread


def _sr_levels(vals: Dict[int, float], high: float, low: float, tol: float = 0.005) -> Tuple[List[int], List[int]]:
    resist, support = [], []
    for p, v in vals.items():
        if np.isnan(v):
            continue
        if abs(high - v) / v < tol:
            resist.append(p)
        if abs(low - v) / v < tol:
            support.append(p)
    return resist, support


def _strength_category(vals: Dict[int, float], close: float) -> int:
    cnt = sum(1 for v in vals.values() if not np.isnan(v) and close > v)
    return 1 + cnt


def ma_system_features(df: pd.DataFrame, periods: List[int] = None) -> MAState:
    periods = periods or DEFAULT_PERIODS
    mas = _calc_ma(df, periods)
    last = df.iloc[-1]
    prev_vals = (
        {p: float(mas[p].iloc[-2]) for p in periods} if len(df) >= 2 else {p: np.nan for p in periods}
    )
    last_vals = {p: float(mas[p].iloc[-1]) for p in periods}
    bull, bear = _alignment(last_vals)
    glue = _glue(last_vals, float(last["close"]))
    diverge_up, diverge_down = _diverge(prev_vals, last_vals)
    resist, support = _sr_levels(last_vals, float(last["high"]), float(last["low"]))
    strength = _strength_category(last_vals, float(last["close"]))
    return MAState(
        bull_alignment=bull,
        bear_alignment=bear,
        glue=glue,
        diverge_up=diverge_up,
        diverge_down=diverge_down,
        resist_levels=sorted(resist),
        support_levels=sorted(support),
        strength_category=strength,
        snapshot=last_vals,
    )
