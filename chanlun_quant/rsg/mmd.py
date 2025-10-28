from __future__ import annotations

from typing import List

from .schema import PenNode, SegmentNode


def tag_mmd_pen(p_seq: List[PenNode]) -> None:
    """
    启发式笔级买卖点标注：
    - 下笔面积缩小且价差收敛 → 1buy；
    - 上笔面积缩小且价差收敛 → 1sell。
    """
    if len(p_seq) < 2:
        return
    prev = p_seq[-2]
    cur = p_seq[-1]
    span_prev = abs(prev.high - prev.low) + 1e-9
    span_cur = abs(cur.high - cur.low) + 1e-9
    if cur.direction == "up" and cur.macd_area_abs < 0.8 * prev.macd_area_abs and span_cur < span_prev:
        if "1buy" not in cur.mmds:
            cur.mmds.append("1buy")
    if cur.direction == "down" and cur.macd_area_abs < 0.8 * prev.macd_area_abs and span_cur < span_prev:
        if "1sell" not in cur.mmds:
            cur.mmds.append("1sell")


def tag_mmd_segment(segment: SegmentNode) -> None:
    """
    启发式段级买卖点标注：
    - 有中枢且靠近上/下沿 → 2buy / 2sell；
    - 段背驰 → 3sell / 3buy。
    """
    if segment.zhongshu:
        zg = segment.zhongshu.get("zg")
        zd = segment.zhongshu.get("zd")
        if zg is not None and zd is not None and segment.macd_eff_price > 0:
            mid = (zg + zd) / 2.0
            if segment.trend_state == "up" and mid < zg:
                if "2buy" not in segment.mmds:
                    segment.mmds.append("2buy")
            if segment.trend_state == "down" and mid > zd:
                if "2sell" not in segment.mmds:
                    segment.mmds.append("2sell")

    if segment.divergence == "trend_div":
        if segment.trend_state == "up":
            if "3sell" not in segment.mmds:
                segment.mmds.append("3sell")
        elif segment.trend_state == "down":
            if "3buy" not in segment.mmds:
                segment.mmds.append("3buy")

