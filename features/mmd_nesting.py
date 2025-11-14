from __future__ import annotations

from typing import List, Sequence

from .segment_index import SegmentIndex


def tag_mmd_for_segment(seg_idx: SegmentIndex, seg_id: str) -> List[str]:
    """
    启发式 MMD 标注（MVP 版）：
    - 1buy / 1sell：震荡或中枢内方向初次反转；
    - 2buy / 2sell：回踩中枢上沿/下沿后延续；
    - 3buy / 3sell：突破前高/前低后的趋势延续；
    简化实现，供后续守护/Agent 引用。
    """
    segment = seg_idx.rsg.segments.get(seg_id)
    if not segment:
        return []

    tags: List[str] = []
    trend = segment.trend_state

    if segment.zhongshu:
        zg = segment.zhongshu.get("zg")
        zd = segment.zhongshu.get("zd")
        if zg is not None and zd is not None:
            if trend == "up":
                tags.append("2buy")
            elif trend == "down":
                tags.append("2sell")
            else:
                tags.append("1buy" if segment.macd_area_dir >= 0 else "1sell")

    if trend == "up" and segment.macd_area_dir > 0 and segment.macd_peak_pos > 0:
        tags.append("3buy")
    if trend == "down" and segment.macd_area_dir < 0 and segment.macd_peak_neg < 0:
        tags.append("3sell")

    if not tags:
        tags.append("1buy" if segment.macd_area_dir >= 0 else "1sell")
    return list(dict.fromkeys(tags))


def cross_level_nesting(
    seg_idx: SegmentIndex,
    high_seg_id: str,
    low_seg_ids: Sequence[str],
    time_win: float = 0.25,
    price_win: float = 0.15,
) -> bool:
    """
    跨级共振窗口：兼顾时间区间和价格区间的重叠比例。
    time_win/price_win 为最低要求。
    """
    high_seg = seg_idx.rsg.segments.get(high_seg_id)
    if not high_seg:
        return False
    high_bounds = _segment_price_bounds(seg_idx, high_seg)
    for low_id in low_seg_ids:
        low_seg = seg_idx.rsg.segments.get(low_id)
        if not low_seg:
            continue
        time_overlap = _overlap_ratio(high_seg.i0, high_seg.i1, low_seg.i0, low_seg.i1)
        price_overlap = True
        if high_seg.zhongshu and low_seg.zhongshu:
            low_bounds = _segment_price_bounds(seg_idx, low_seg)
            price_overlap = (
                _price_overlap_ratio(
                    high_seg.zhongshu.get("zg", high_bounds[0]),
                    high_seg.zhongshu.get("zd", high_bounds[1]),
                    low_seg.zhongshu.get("zg", low_bounds[0]),
                    low_seg.zhongshu.get("zd", low_bounds[1]),
                )
                >= price_win
            )
        if time_overlap >= time_win and price_overlap:
            return True
    return False


def _overlap_ratio(a0: int, a1: int, b0: int, b1: int) -> float:
    inter = max(0, min(a1, b1) - max(a0, b0) + 1)
    span = max(1, a1 - a0 + 1)
    return inter / span


def _price_overlap_ratio(zg1: float, zd1: float, zg2: float, zd2: float) -> float:
    top = min(zg1, zg2)
    bot = max(zd1, zd2)
    inter = max(0.0, top - bot)
    span = max(1e-9, zg1 - zd1)
    return inter / span


def _segment_price_bounds(seg_idx: SegmentIndex, segment) -> tuple[float, float]:
    highs: List[float] = []
    lows: List[float] = []
    for pen_id in segment.pens:
        pen = seg_idx.rsg.pens.get(pen_id)
        if pen:
            highs.append(pen.high)
            lows.append(pen.low)
    if not highs or not lows:
        return (0.0, 0.0)
    return max(highs), min(lows)
