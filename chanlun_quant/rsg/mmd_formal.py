from __future__ import annotations

from typing import List, Optional

from ..config import MMDStrictCfg
from .schema import SegmentNode


def _zs_span(segment: SegmentNode) -> float:
    if not segment.zhongshu:
        return 0.0
    return max(1e-12, segment.zhongshu["zg"] - segment.zhongshu["zd"])


def _zs_pos_ratio(segment: SegmentNode) -> float:
    if not segment.zhongshu:
        return 0.5
    zg = segment.zhongshu["zg"]
    zd = segment.zhongshu["zd"]
    zm = segment.zhongshu["zm"]
    return (zm - zd) / max(1e-12, zg - zd)


def _macd_expand(prev: SegmentNode, cur: SegmentNode, cfg: MMDStrictCfg) -> bool:
    ok_abs = cur.macd_area_abs > cfg.macd_expand_ratio * max(1e-12, prev.macd_area_abs)
    ok_peak = (
        abs(cur.macd_peak_pos) > cfg.macd_expand_ratio * abs(prev.macd_peak_pos)
        or abs(cur.macd_peak_neg) > cfg.macd_expand_ratio * abs(prev.macd_peak_neg)
    )
    ok_eff = cur.macd_eff_price > cfg.macd_expand_ratio * max(1e-12, prev.macd_eff_price)
    return ok_abs or ok_peak or ok_eff


def _macd_decay(prev: SegmentNode, cur: SegmentNode, decay: float) -> bool:
    prev_dir = abs(prev.macd_area_dir)
    cur_dir = abs(cur.macd_area_dir)
    return cur_dir < decay * max(1e-12, prev_dir)


def tag_2_buy_sell(cur: SegmentNode, cfg: MMDStrictCfg) -> Optional[str]:
    if not cur.zhongshu:
        return None
    pos_ratio = _zs_pos_ratio(cur)
    if cur.trend_state == "up" and (1.0 - pos_ratio) <= cfg.leave_ratio and cur.macd_eff_price > 0:
        return "2buy"
    if cur.trend_state == "down" and pos_ratio <= cfg.leave_ratio and cur.macd_eff_price > 0:
        return "2sell"
    return None


def tag_3_buy_sell(prev: SegmentNode, cur: SegmentNode, cfg: MMDStrictCfg) -> Optional[str]:
    if cur.divergence == "trend_div":
        if cur.trend_state == "up":
            return "3sell"
        if cur.trend_state == "down":
            return "3buy"
    if cur.trend_state == "up" and _macd_expand(prev, cur, cfg):
        return "3buy"
    if cur.trend_state == "down" and _macd_expand(prev, cur, cfg):
        return "3sell"
    return None


def tag_3weak(prev: SegmentNode, cur: SegmentNode, cfg: MMDStrictCfg) -> Optional[str]:
    if prev.trend_state != cur.trend_state:
        return None
    if cur.trend_state == "up" and not _macd_expand(prev, cur, cfg):
        return "3weak_buy"
    if cur.trend_state == "down" and not _macd_expand(prev, cur, cfg):
        return "3weak_sell"
    return None


def tag_1_buy_sell(prev: SegmentNode, cur: SegmentNode, cfg: MMDStrictCfg) -> Optional[str]:
    if not cur.zhongshu:
        return None
    if cur.trend_state == "up" and _macd_decay(prev, cur, cfg.pen_area_decay):
        return "1sell"
    if cur.trend_state == "down" and _macd_decay(prev, cur, cfg.pen_area_decay):
        return "1buy"
    return None


def apply_formal_mmd_on_segments(segments: List[SegmentNode], cfg: MMDStrictCfg) -> None:
    for segment in segments:
        tag = tag_2_buy_sell(segment, cfg)
        if tag and tag not in segment.mmds:
            segment.mmds.append(tag)

    for idx in range(1, len(segments)):
        prev = segments[idx - 1]
        cur = segments[idx]
        if prev.trend_state != cur.trend_state:
            continue
        tag3 = tag_3_buy_sell(prev, cur, cfg)
        if tag3 and tag3 not in cur.mmds:
            cur.mmds.append(tag3)
        tag1 = tag_1_buy_sell(prev, cur, cfg)
        if tag1 and tag1 not in cur.mmds:
            cur.mmds.append(tag1)
        tagw = tag_3weak(prev, cur, cfg)
        if tagw and tagw not in cur.mmds:
            cur.mmds.append(tagw)
