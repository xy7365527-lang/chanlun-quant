from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple


def _prefix_sum(values: Sequence[float]) -> List[float]:
    """构造前缀和数组，便于 O(1) 查询区间面积。"""
    ps: List[float] = [0.0]
    total = 0.0
    for val in values:
        total += float(val)
        ps.append(total)
    return ps


class MACDArea:
    """MACD 面积前缀和容器。hist 为 DIF-DEA 柱状图。"""

    def __init__(self, hist: Iterable[float]):
        hist_list = [float(val) for val in hist]
        self.hist: List[float] = hist_list
        pos = [max(x, 0.0) for x in hist_list]
        neg = [max(-x, 0.0) for x in hist_list]
        abs_ = [abs(x) for x in hist_list]
        self.ps_pos = _prefix_sum(pos)
        self.ps_neg = _prefix_sum(neg)
        self.ps_abs = _prefix_sum(abs_)

    @staticmethod
    def _sum(ps: Sequence[float], i0: int, i1: int) -> float:
        """查询区间 [i0, i1] 的前缀和差值。"""
        if i0 > i1:
            return 0.0
        start = max(i0, 0)
        end = min(i1, len(ps) - 2)
        if start > end:
            return 0.0
        return float(ps[end + 1] - ps[start])

    def macd_area_span(self, i0: int, i1: int) -> Tuple[float, float, float, float, float, float]:
        """返回 (正面积, 负面积, 绝对面积, 净面积, 峰值正, 峰值负)。"""
        a_pos = self._sum(self.ps_pos, i0, i1)
        a_neg = self._sum(self.ps_neg, i0, i1)
        a_abs = self._sum(self.ps_abs, i0, i1)
        span = self.hist[max(i0, 0) : min(i1, len(self.hist) - 1) + 1]
        peak_pos = max(span) if span else 0.0
        peak_neg = min(span) if span else 0.0
        net = a_pos - a_neg
        return a_pos, a_neg, a_abs, net, peak_pos, peak_neg


def macd_density(area_abs: float, bars: int) -> float:
    """面积密度：单位时间（K 线数量）面积。"""
    return area_abs / max(bars, 1)


def macd_efficiency(area_abs: float, price_span: float) -> float:
    """面积效率：单位价差面积，避免除零情况。"""
    denom = abs(price_span)
    if denom <= 0.0:
        denom = 1e-9
    return area_abs / denom

