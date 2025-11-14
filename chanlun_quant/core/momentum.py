from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from chanlun_quant.types import Segment, Stroke, Trend


def ema(values: List[float], period: int) -> List[float]:
    """
    标准EMA：alpha=2/(period+1)，以第一项为初值，返回与 values 等长列表。
    """
    if period <= 1 or len(values) == 0:
        return list(values)
    alpha = 2.0 / (period + 1.0)
    out: List[float] = [values[0]]
    for i in range(1, len(values)):
        out.append(alpha * values[i] + (1 - alpha) * out[-1])
    return out


def compute_macd(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, List[float]]:
    """
    经典MACD：DIF = EMA(fast) - EMA(slow), DEA = EMA(DIF, signal), HIST = DIF - DEA
    返回 {"dif":[], "dea":[], "hist":[]}
    """
    if len(closes) == 0:
        return {"dif": [], "dea": [], "hist": []}
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    dif = [f - s for f, s in zip(ema_fast, ema_slow)]
    dea = ema(dif, signal)
    hist = [d - e for d, e in zip(dif, dea)]
    return {"dif": dif, "dea": dea, "hist": hist}


def area_between(macd: Dict[str, List[float]], start_idx: int, end_idx: int, mode: str = "hist") -> float:
    """
    在闭区间[start..end]上按指定 mode 计算 MACD 面积：
    - "hist": 累加 (DIF-DEA) == hist
    - "dif":  累加 DIF       == EMA快线-慢线面积
    - "abs_hist": 累加 |DIF-DEA|
    """
    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx
    dif = macd.get("dif", [])
    dea = macd.get("dea", [])
    hist = macd.get("hist", [])
    if mode == "hist":
        seq = hist
    elif mode == "dif":
        seq = dif
    elif mode == "abs_hist":
        if not dif or not dea:
            raise ValueError("dif/dea not available for abs_hist mode")
        seq = [abs(d - e) for d, e in zip(dif, dea)]
    else:
        raise ValueError(f"unknown area mode: {mode}")
    n = len(seq)
    if n == 0:
        return 0.0
    start = max(0, min(start_idx, n - 1))
    end = max(0, min(end_idx, n - 1))
    if start > end:
        start, end = end, start
    return float(sum(seq[start : end + 1]))


def area_for_stroke(macd: Dict[str, List[float]], stroke: Stroke, mode: str = "hist") -> float:
    return area_between(macd, stroke.start_bar_index, stroke.end_bar_index, mode=mode)


def area_for_segment(macd: Dict[str, List[float]], seg: Segment, mode: str = "hist") -> float:
    return area_between(macd, seg.start_index, seg.end_index, mode=mode)


def area_for_segments(macd: Dict[str, List[float]], segments: List[Segment], mode: str = "hist") -> float:
    """多个 Segment 的面积聚合（求和），允许非连续分段。"""
    total = 0.0
    for seg in segments:
        total += area_for_segment(macd, seg, mode=mode)
    return float(total)


def area_for_trend(macd: Dict[str, List[float]], trend: Trend, mode: str = "hist") -> float:
    """趋势面积：等于其包含的若干 Segment 面积之和。"""
    return area_for_segments(macd, trend.segments, mode=mode)


def _segment_extremes(seg: Segment) -> Tuple[float, float]:
    """求线段的最高价与最低价，基于其中笔的 high/low。"""
    hi = max(st.high for st in seg.strokes)
    lo = min(st.low for st in seg.strokes)
    return hi, lo


def is_trend_divergent(
    segA: Segment,
    segC: Segment,
    macd: Dict[str, List[float]],
    threshold: float = 0.8,
    area_mode: str = "hist",
) -> bool:
    """
    趋势背驰（A→C 同向）：
    - 新极值 + 面积衰减（按 area_mode 比较）：|Area(C)| < threshold * |Area(A)|
    """
    area_A = area_for_segment(macd, segA, mode=area_mode)
    area_C = area_for_segment(macd, segC, mode=area_mode)
    hi_A, lo_A = _segment_extremes(segA)
    hi_C, lo_C = _segment_extremes(segC)
    if segC.direction == "up":
        new_extreme_ok = hi_C > hi_A
    else:
        new_extreme_ok = lo_C < lo_A
    area_ok = abs(area_C) < threshold * abs(area_A)
    return bool(new_extreme_ok and area_ok)


def ma_strength_diff(
    fast_ema: List[float],
    slow_ema: List[float],
    start_index: int,
    end_index: int,
) -> float:
    """Accumulate EMA spread area across an index window."""
    if not fast_ema or not slow_ema:
        return 0.0
    if len(fast_ema) != len(slow_ema):
        raise ValueError("EMA sequences must have equal length")
    if start_index > end_index:
        start_index, end_index = end_index, start_index
    start = max(0, start_index)
    end = min(len(fast_ema) - 1, end_index)
    total = 0.0
    for idx in range(start, end + 1):
        total += fast_ema[idx] - slow_ema[idx]
    return total


class MomentumEvaluator:
    """MACD/EMA momentum helper for ChanLun structures."""

    def __init__(self, closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        if not closes:
            raise ValueError("MomentumEvaluator requires non-empty closing prices")
        self._closes = closes
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self._macd = compute_macd(closes, fast=fast, slow=slow, signal=signal)

    @property
    def macd(self) -> Dict[str, List[float]]:
        return self._macd

    def macd_area(self, start_index: int, end_index: int, mode: str = "hist") -> float:
        return area_between(self._macd, start_index, end_index, mode=mode)

    def segment_metrics(self, segment: Segment, mode: str = "hist") -> Dict[str, float]:
        area = area_for_segment(self._macd, segment, mode=mode)
        length = max(1, segment.end_index - segment.start_index)
        density = area / length
        hi, lo = _segment_extremes(segment)
        return {
            "area": area,
            "density": density,
            "length": float(length),
            "high": hi,
            "low": lo,
        }

    def compare_segments(
        self,
        seg_a: Segment,
        seg_c: Segment,
        threshold: float = 0.8,
        mode: str = "hist",
    ) -> Dict[str, float | bool]:
        area_a = area_for_segment(self._macd, seg_a, mode=mode)
        area_c = area_for_segment(self._macd, seg_c, mode=mode)
        ratio = abs(area_c) / max(abs(area_a), 1e-9)
        divergent = is_trend_divergent(seg_a, seg_c, self._macd, threshold=threshold, area_mode=mode)
        return {
            "is_divergent": divergent,
            "area_a": area_a,
            "area_c": area_c,
            "area_ratio": ratio,
        }

    def ema_spread(
        self,
        fast_period: int = 5,
        slow_period: int = 20,
        start_index: Optional[int] = None,
        end_index: Optional[int] = None,
    ) -> Dict[str, float | int | str]:
        fast_series = ema(self._closes, fast_period)
        slow_series = ema(self._closes, slow_period)
        start = 0 if start_index is None else max(0, start_index)
        end = len(self._closes) - 1 if end_index is None else min(len(self._closes) - 1, end_index)
        area = ma_strength_diff(fast_series, slow_series, start, end)
        spread = fast_series[end] - slow_series[end]
        trend = "up" if spread > 0 else "down" if spread < 0 else "flat"
        return {
            "area": area,
            "spread": spread,
            "trend": trend,
            "fast": fast_series[end],
            "slow": slow_series[end],
            "start": start,
            "end": end,
        }

    def momentum_state(
        self,
        segment: Segment,
        mode: str = "hist",
        divergence_threshold: float = 0.8,
    ) -> Dict[str, object]:
        metrics = self.segment_metrics(segment, mode=mode)
        bias = "up" if metrics["area"] > 0 else "down" if metrics["area"] < 0 else "flat"
        strength = abs(metrics["density"])
        tail_span = metrics["high"] - metrics["low"]
        divergence_info = {
            "has_divergence": False,
            "area_ratio": 1.0,
        }
        if segment.child_segments:
            base = segment.child_segments[0]
            divergence = self.compare_segments(base, segment, threshold=divergence_threshold, mode=mode)
            divergence_info = {
                "has_divergence": bool(divergence["is_divergent"]),
                "area_ratio": float(divergence["area_ratio"]),
            }
        return {
            "direction": segment.direction,
            "bias": bias,
            "strength": strength,
            "tail_span": tail_span,
            "divergence": divergence_info,
        }

    def to_llm_context(self, segment: Segment, mode: str = "hist") -> Dict[str, object]:
        metrics = self.segment_metrics(segment, mode=mode)
        ema_snapshot = self.ema_spread()
        return {
            "segment_direction": segment.direction,
            "macd_area": metrics["area"],
            "macd_density": metrics["density"],
            "price_high": metrics["high"],
            "price_low": metrics["low"],
            "ema_trend": ema_snapshot["trend"],
            "ema_spread": ema_snapshot["spread"],
            "ema_area": ema_snapshot["area"],
        }
