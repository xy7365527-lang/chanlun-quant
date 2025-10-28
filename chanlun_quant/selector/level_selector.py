from __future__ import annotations

from statistics import fmean
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from ..rsg.schema import Level, RSG

DEFAULT_ORDER: List[Level] = ["M1", "M5", "M15", "H1", "H4", "D1", "W1"]


def _order_idx(level: Level) -> int:
    return DEFAULT_ORDER.index(level)


def _normalized_levels(levels: Sequence[Level]) -> List[Level]:
    """按默认顺序排序去重。"""
    ordered = sorted(set(levels), key=_order_idx)
    return ordered


def _rough_bi_density(rsg: RSG, level: Level) -> float:
    """估算笔密度：笔数 / 总 bars。"""
    pen_ids = [pid for pid in rsg.pens if rsg.pens[pid].level == level]
    if not pen_ids:
        return 0.0
    bars_span = max(
        (rsg.pens[pid].i1 for pid in pen_ids),
        default=0,
    ) - min((rsg.pens[pid].i0 for pid in pen_ids), default=0) + 1
    return len(pen_ids) / max(bars_span, 1)


def _rough_seg_density(rsg: RSG, level: Level) -> float:
    """估算线段密度：线段数 / 总 bars。"""
    seg_ids = [sid for sid in rsg.segments if rsg.segments[sid].level == level]
    if not seg_ids:
        return 0.0
    bars_span = max(
        (rsg.segments[sid].i1 for sid in seg_ids),
        default=0,
    ) - min((rsg.segments[sid].i0 for sid in seg_ids), default=0) + 1
    return len(seg_ids) / max(bars_span, 1)


def _zhongshu_coverage(rsg: RSG, level: Level) -> float:
    """计算中枢覆盖率：包含中枢的段占比。"""
    segs = [seg for seg in rsg.segments.values() if seg.level == level]
    if not segs:
        return 0.0
    with_zhongshu = sum(1 for seg in segs if seg.zhongshu)
    return with_zhongshu / len(segs)


def _nesting_quality(rsg: RSG, level: Level) -> float:
    """线段嵌套质量：下级线段被高级线段覆盖的平均比例。"""
    segs = [seg for seg in rsg.segments.values() if seg.level == level]
    if not segs:
        return 0.0
    parent_map: Dict[str, List[str]] = {}
    for edge in rsg.edges:
        parent_map.setdefault(edge["parent"], []).append(edge["child"])
    qualities: List[float] = []
    for seg in segs:
        child_segments = [
            child_id
            for child_id in parent_map.get(seg.id, [])
            if child_id in rsg.segments and rsg.segments[child_id].level != level
        ]
        if not child_segments:
            continue
        overlaps = 0
        for child_id in child_segments:
            child = rsg.segments[child_id]
            if seg.i0 <= child.i0 and child.i1 <= seg.i1:
                overlaps += 1
        qualities.append(overlaps / len(child_segments))
    return fmean(qualities) if qualities else 0.0


def _atr_regime(datafeed: Callable[[str, Level], float], symbol: str, level: Level) -> float:
    """从 datafeed 拉取 ATR，若不可用则返回 0。"""
    try:
        return float(datafeed(symbol, level))
    except Exception:
        return 0.0


def select_levels(
    symbol: str,
    datafeed: Callable[[str, Level], float],
    candidates: Sequence[Level],
    max_levels: int = 4,
) -> List[Level]:
    """基于结构密度/中枢覆盖/嵌套质量/ATR 的规则选择级别组合（MVP 近似）。"""
    if not candidates:
        raise ValueError("缺少候选级别。")
    ordered_candidates = _normalized_levels(candidates)

    base = "M15" if "M15" in ordered_candidates else ordered_candidates[0]
    selection: List[Level] = [base]

    atr_value = _atr_regime(datafeed, symbol, base)
    base_idx = _order_idx(base)
    if atr_value > 2.0 and base_idx > 0:
        selection.insert(0, ordered_candidates[max(base_idx - 1, 0)])

    for level in ordered_candidates:
        if _order_idx(level) > _order_idx(selection[-1]):
            selection.append(level)
        if len(selection) >= max_levels:
            break

    return selection


def post_validate_levels(rsg: RSG, levels: Sequence[Level]) -> List[Level]:
    """就近复核：若末级线段特征序列不稳/中枢覆盖高，则抬升起点或插桥级。"""
    if not levels:
        return []

    ordered_levels = _normalized_levels(levels)
    reasons: List[str] = []

    def _feature_variance(level: Level) -> float:
        segs = [seg for seg in rsg.segments.values() if seg.level == level]
        if not segs:
            return 0.0
        lengths = [len(seg.feature_seq) for seg in segs if seg.feature_seq]
        if not lengths:
            return 0.0
        avg = fmean(lengths)
        return fmean([(length - avg) ** 2 for length in lengths])

    adjusted = list(ordered_levels)
    lowest = adjusted[0]
    lowest_pen_density = _rough_bi_density(rsg, lowest)
    lowest_seg_density = _rough_seg_density(rsg, lowest)
    lowest_feature_var = _feature_variance(lowest)
    lowest_coverage = _zhongshu_coverage(rsg, lowest)

    noisy_low = (
        lowest_pen_density > 0.4
        or lowest_seg_density > 0.25
        or lowest_feature_var > 2.0
    )
    crowded_low = lowest_coverage > 0.7
    if noisy_low or crowded_low:
        idx = DEFAULT_ORDER.index(lowest)
        if idx + 1 < len(DEFAULT_ORDER):
            next_level = DEFAULT_ORDER[idx + 1]
            if next_level in ordered_levels:
                adjusted[0] = next_level
                reasons.append(
                    f"{lowest} noisy:{lowest_pen_density:.2f}/{lowest_seg_density:.2f} or crowded:{lowest_coverage:.2f} → promote {next_level}"
                )

    highest = adjusted[-1]
    coverage = _zhongshu_coverage(rsg, highest)
    if coverage < 0.2:
        idx_high = DEFAULT_ORDER.index(highest)
        if idx_high + 1 < len(DEFAULT_ORDER):
            bridge = DEFAULT_ORDER[idx_high + 1]
            if bridge not in adjusted:
                adjusted.append(bridge)
                adjusted.sort(key=_order_idx)
                reasons.append(f"{highest} coverage {coverage:.2f} too low → insert {bridge}")

    if not reasons:
        reasons.append("ok")

    rsg.build_info["level_selector_reason"] = "; ".join(reasons)

    return adjusted
