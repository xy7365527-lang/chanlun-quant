from __future__ import annotations
from typing import List, Optional
from chanlun_quant.types import Bar, Fractal, Stroke, Direction


def _bar_pos_map(bars: List[Bar]) -> dict[int, int]:
    """
    将 Bar.index -> 在 bars 列表中的位置下标（pos）。
    假设 Bar.index 单调递增且唯一；若不唯一，取首次出现。
    """
    pos = {}
    for i, b in enumerate(bars):
        if b.index not in pos:
            pos[b.index] = i
    return pos


def _slice_high_low(bars: List[Bar], pos_map: dict[int, int], start_bar_index: int, end_bar_index: int) -> tuple[float, float]:
    """在闭区间 [start..end] 计算该区间的 (high, low)。"""
    si = pos_map.get(start_bar_index)
    ei = pos_map.get(end_bar_index)
    if si is None or ei is None:
        raise ValueError("start_bar_index or end_bar_index not found in bars pos map")
    if si > ei:
        si, ei = ei, si
    highs = (b.high for b in bars[si:ei+1])
    lows  = (b.low  for b in bars[si:ei+1])
    return (max(highs), min(lows))


def _opposite(fr: Fractal, fr2: Fractal) -> bool:
    return fr.type != fr2.type


def _direction(start: Fractal, end: Fractal) -> Direction:
    # bottom->top 为 up；top->bottom 为 down
    return "up" if (start.type == "bottom" and end.type == "top") else "down"


def _exceed_ok(start: Fractal, end: Fractal, dir_: Direction) -> bool:
    if dir_ == "up":
        return end.price > start.price
    return end.price < start.price


def build_strokes(fractals: List[Fractal], bars: List[Bar], min_bars_per_pen: int = 5) -> List[Stroke]:
    """
    根据分型序列构建笔：
    - 相邻异类分型配对；
    - 满足最小 K 数要求 + 超越约束；
    - 计算区间 high/low。
    """
    res: List[Stroke] = []
    if not fractals or not bars:
        return res

    # 按 bar_index 升序保证时间顺序
    frs = sorted(fractals, key=lambda f: f.bar_index)
    pos_map = _bar_pos_map(bars)

    i = 0
    n = len(frs)
    while i < n - 1:
        start = frs[i]
        # 寻找下一个异类分型作为候选 end
        j = i + 1
        matched: Optional[Stroke] = None
        while j < n:
            end = frs[j]
            if not _opposite(start, end):
                j += 1
                continue
            dir_ = _direction(start, end)

            # 最小成笔 K 数：bars[end].index - bars[start].index >= min_bars_per_pen - 1
            bar_span = end.bar_index - start.bar_index
            if bar_span < (min_bars_per_pen - 1):
                j += 1
                continue

            # 超越约束
            if not _exceed_ok(start, end, dir_):
                j += 1
                continue

            # 计算区间 high/low
            hi, lo = _slice_high_low(bars, pos_map, start.bar_index, end.bar_index)

            stroke = Stroke(
                start_fractal=start,
                end_fractal=end,
                direction=dir_,
                high=hi,
                low=lo,
                start_bar_index=start.bar_index,
                end_bar_index=end.bar_index,
                id=f"{start.bar_index}->{end.bar_index}",
                level=end.level or start.level
            )
            matched = stroke
            break  # 找到最近的合法 end 即成笔

        if matched:
            res.append(matched)
            # 下一笔从刚刚的 end 开始
            # 将 i 移动到匹配 end 的位置，继续向后找下一笔
            # 保证笔之间不重叠地向前推进
            i = j
        else:
            # 当前 start 无法形成笔，向后移动起点
            i += 1

    return res
