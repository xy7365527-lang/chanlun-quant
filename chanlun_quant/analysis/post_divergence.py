from __future__ import annotations

from typing import List, Optional, Tuple

from chanlun_quant.types import Central, Direction, PostDivergenceOutcome, Segment


def _segment_price_range(segment: Segment) -> Tuple[float, float]:
    highs = [stroke.high for stroke in segment.strokes]
    lows = [stroke.low for stroke in segment.strokes]
    hi = max(highs) if highs else 0.0
    lo = min(lows) if lows else 0.0
    return lo, hi


def _overlap_ratio(segments: List[Segment]) -> float:
    if len(segments) < 3:
        return 0.0
    lows = []
    highs = []
    for seg in segments[:3]:
        lo, hi = _segment_price_range(seg)
        lows.append(lo)
        highs.append(hi)
    overlap_low = max(lows)
    overlap_high = min(highs)
    if overlap_high <= overlap_low:
        return 0.0
    total_range = max(highs) - min(lows)
    if total_range <= 0:
        return 0.0
    return (overlap_high - overlap_low) / total_range


def analyze_post_divergence(
    prev_central: Optional[Central],
    post_segments: List[Segment],
    *,
    overlap_threshold: float = 0.7,
    leave_ratio: float = 0.3,
    window: int = 3,
) -> PostDivergenceOutcome:
    """
    根据背驰后的走势结构判断演化路径：盘整/中枢扩展/新趋势。
    :param prev_central: 背驰前最后一个中枢（可选）。
    :param post_segments: 背驰后同级别线段序列（按时间升序）。
    :param overlap_threshold: 判定盘整的重叠比例阈值。
    :param leave_ratio: 判定有效离开中枢所需的比例（相对于中枢高度）。
    :param window: 计算重叠率时采样的线段数量。
    """
    sampled = post_segments[:window]
    overlap_rate = _overlap_ratio(sampled)

    left_central = False
    leave_direction: Optional[str] = None
    leave_margin = 0.0
    if prev_central:
        height = max(1e-6, prev_central.zg - prev_central.zd)
        leave_margin = height * leave_ratio
        for seg in post_segments:
            lo, hi = _segment_price_range(seg)
            if hi > prev_central.zg + leave_margin:
                left_central = True
                leave_direction = "up"
                break
            if lo < prev_central.zd - leave_margin:
                left_central = True
                leave_direction = "down"
                break

    classification: str
    notes: str
    new_trend_direction: Optional[Direction] = None

    if prev_central and sampled:
        inside_original = all(
            prev_central.zd <= _segment_price_range(seg)[0] <= prev_central.zg
            and prev_central.zd <= _segment_price_range(seg)[1] <= prev_central.zg
            for seg in sampled
        )
    else:
        inside_original = False

    if inside_original:
        classification = "central_extension"
        notes = "走势仍在原中枢区间内震荡，倾向中枢扩展"
    elif sampled and overlap_rate >= overlap_threshold:
        classification = "consolidation"
        notes = "背驰后三段高度重叠，倾向盘整或筑势"
    elif left_central:
        classification = "new_trend"
        first_direction = sampled[0].direction if sampled else post_segments[0].direction if post_segments else None
        new_trend_direction = first_direction
        if leave_direction == "up":
            notes = "价格有效上破前中枢，倾向新上升段"
        elif leave_direction == "down":
            notes = "价格有效下破前中枢，倾向新下跌段"
        else:
            notes = "价格离开前中枢，倾向新趋势"
    else:
        classification = "uncertain"
        notes = "缺乏足够重叠或离开信号，走势待观察"

    evidence = {
        "overlap_rate": overlap_rate,
        "sampled_count": len(sampled),
        "max_index_gap": (sampled[-1].end_index - sampled[0].start_index) if len(sampled) >= 2 else 0,
        "leave_margin": leave_margin,
        "leave_direction": leave_direction,
    }

    return PostDivergenceOutcome(
        classification=classification,
        overlap_rate=overlap_rate,
        left_central=left_central,
        new_trend_direction=new_trend_direction,
        notes=notes,
        evidence=evidence,
    )
