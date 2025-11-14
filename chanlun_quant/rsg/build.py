from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .metrics import MACDArea, macd_density, macd_efficiency
from .mmd import tag_mmd_pen, tag_mmd_segment
from .mmd_rules import apply_strict_mmd_on_segments
from .mmd_formal import apply_formal_mmd_on_segments
from ..config import Config
from .schema import Divergence, Edge, Level, PenNode, RSG, SegmentNode, TrendNode

Bar = Mapping[str, float]
Fractal = Tuple[int, str]

__all__ = [
    "Bar",
    "Fractal",
    "build_level_pens_segments",
    "build_multi_levels",
]


@dataclass(frozen=True)
class _SegmentDraft:
    """线段草稿：用于暂存笔列表与统计信息。"""

    pen_ids: List[str]
    pens: List[PenNode]
    feature_seq: List[str]


def _find_fractals(
    highs: Sequence[float],
    lows: Sequence[float],
    min_k: int = 3,
) -> List[Fractal]:
    """简化分型识别：返回 [(idx, 'top'|'bot'), ...]，只做局部极值判断。"""
    out: List[Fractal] = []
    n = len(highs)
    if n == 0:
        return out
    window = max(1, min_k // 2)
    for idx in range(window, n - window):
        scope = slice(idx - window, idx + window + 1)
        local_highs = highs[scope]
        local_lows = lows[scope]
        center_high = highs[idx]
        center_low = lows[idx]
        if center_high >= max(local_highs):
            out.append((idx, "top"))
        if center_low <= min(local_lows):
            out.append((idx, "bot"))
    return out


def _aggregate_macd(
    macd: MACDArea,
    i0: int,
    i1: int,
) -> Tuple[float, float, float, float, float, float]:
    """便捷聚合 MACD 面积族。"""
    start = min(i0, i1)
    end = max(i0, i1)
    return macd.macd_area_span(start, end)


def _build_pens(
    fractals: Sequence[Fractal],
    highs: Sequence[float],
    lows: Sequence[float],
    level: Level,
    macd: MACDArea,
) -> List[PenNode]:
    """根据分型序列生成相邻笔，自动选择极值更优的分型点。"""
    pens: List[PenNode] = []
    anchor: Optional[Fractal] = None
    for idx, fract_type in fractals:
        if anchor is None:
            anchor = (idx, fract_type)
            continue

        prev_idx, prev_type = anchor
        if prev_type == "top" and fract_type == "bot":
            start = min(prev_idx, idx)
            end = max(prev_idx, idx)
            high = highs[prev_idx]
            low = lows[idx]
            a_pos, a_neg, a_abs, a_net, p_pos, p_neg = _aggregate_macd(macd, start, end)
            pen = PenNode(
                id=f"pen_{level}_{len(pens)}",
                level=level,
                i0=start,
                i1=end,
                high=float(high),
                low=float(low),
                direction="down",
                macd_area_pos=a_pos,
                macd_area_neg=a_neg,
                macd_area_abs=a_abs,
                macd_area_net=a_net,
                macd_peak_pos=p_pos,
                macd_peak_neg=p_neg,
                macd_dens=macd_density(a_abs, end - start + 1),
                macd_eff_price=macd_efficiency(a_abs, high - low),
            )
            pens.append(pen)
            tag_mmd_pen(pens)
            anchor = (idx, fract_type)
            continue

        if prev_type == "bot" and fract_type == "top":
            start = min(prev_idx, idx)
            end = max(prev_idx, idx)
            high = highs[idx]
            low = lows[prev_idx]
            a_pos, a_neg, a_abs, a_net, p_pos, p_neg = _aggregate_macd(macd, start, end)
            pen = PenNode(
                id=f"pen_{level}_{len(pens)}",
                level=level,
                i0=start,
                i1=end,
                high=float(high),
                low=float(low),
                direction="up",
                macd_area_pos=a_pos,
                macd_area_neg=a_neg,
                macd_area_abs=a_abs,
                macd_area_net=a_net,
                macd_peak_pos=p_pos,
                macd_peak_neg=p_neg,
                macd_dens=macd_density(a_abs, end - start + 1),
                macd_eff_price=macd_efficiency(a_abs, high - low),
            )
            pens.append(pen)
            tag_mmd_pen(pens)
            anchor = (idx, fract_type)
            continue

        # 同向分型，保留更极端的点
        if fract_type == "top" and highs[idx] >= highs[prev_idx]:
            anchor = (idx, fract_type)
        elif fract_type == "bot" and lows[idx] <= lows[prev_idx]:
            anchor = (idx, fract_type)

    return pens


def _close_segment_candidate(candidate: _SegmentDraft) -> Optional[SegmentNode]:
    """尝试将草稿转为线段节点。"""
    if len(candidate.pens) < 2:
        return None
    pens = candidate.pens
    level = pens[0].level
    i0 = pens[0].i0
    i1 = pens[-1].i1
    high = max(pen.high for pen in pens)
    low = min(pen.low for pen in pens)
    return SegmentNode(
        id=f"seg_{level}_{i0}_{i1}",
        level=level,
        i0=i0,
        i1=i1,
        pens=list(candidate.pen_ids),
        feature_seq=list(candidate.feature_seq),
        trend_state="range",
        zhongshu=None,
        divergence="none",
        macd_area_dir=0.0,
        macd_area_abs=0.0,
        macd_area_net=0.0,
        macd_peak_pos=0.0,
        macd_peak_neg=0.0,
        macd_dens=0.0,
        macd_eff_price=0.0,
        mmds=[],
        tags=[],
    )


def _unique_segments_by_sx(pens: Sequence[PenNode]) -> List[SegmentNode]:
    """特征序列唯一化的近似实现，支持最小可行线段输出。"""
    segments: List[SegmentNode] = []
    current_pens: List[PenNode] = []
    current_seq: List[str] = []
    for pen in pens:
        marker = "S" if pen.direction == "up" else "X"
        current_pens.append(pen)
        current_seq.append(marker)

        if len(current_pens) < 3:
            continue

        last = current_pens[-1]
        prev = current_pens[-2]
        prev_high = max(p.high for p in current_pens[:-1])
        prev_low = min(p.low for p in current_pens[:-1])
        breakout = (
            last.direction == "up" and last.high >= prev_high
        ) or (last.direction == "down" and last.low <= prev_low)

        if marker != current_seq[-2] and breakout:
            draft = _SegmentDraft(
                pen_ids=[pen.id for pen in current_pens],
                pens=list(current_pens),
                feature_seq=list(current_seq),
            )
            segment = _close_segment_candidate(draft)
            if segment:
                # 以最后一笔方向粗略定义线段趋势
                last_dir = current_pens[-1].direction
                segment.trend_state = last_dir  # type: ignore[assignment]
                segments.append(segment)
                # 保留最后两笔，以便下一段继承趋势
                current_pens = current_pens[-2:]
                current_seq = current_seq[-2:]

    return segments


def _extract_series(bars: Sequence[Bar], key: str) -> List[float]:
    """从 bar 序列提取高低价, 允许缺失字段时兜底。"""
    series: List[float] = []
    for bar in bars:
        value = bar.get(key)
        if value is None and key == "close":
            high = bar.get("high")
            low = bar.get("low")
            if high is not None and low is not None:
                value = (high + low) / 2.0
        if value is None:
            raise ValueError(f"缺少字段 {key}，无法构建 RSG。")
        series.append(float(value))
    return series


def _build_edges(segments: Sequence[SegmentNode]) -> List[Edge]:
    """生成段-笔关系边，便于后续注入 RSG 容器。"""
    edges: List[Edge] = []
    for segment in segments:
        for pen_id in segment.pens:
            edges.append(
                {
                    "parent": segment.id,
                    "child": pen_id,
                    "rel": "segment_pen",
                    "lv": (segment.level, segment.level),
                }
            )
    return edges


def build_level_pens_segments(
    bars: Sequence[Bar],
    level: Level,
    macd_hist: Sequence[float],
    min_fractal_k: int = 3,
) -> Tuple[List[PenNode], List[SegmentNode], List[Edge]]:
    """构建指定级别的笔与线段，返回节点及父子边。"""
    if len(bars) != len(macd_hist):
        raise ValueError("bars 与 macd_hist 长度不一致。")
    highs = _extract_series(bars, "high")
    lows = _extract_series(bars, "low")
    fractals = _find_fractals(highs, lows, min_k=min_fractal_k)
    macd = MACDArea(macd_hist)
    pens = _build_pens(fractals, highs, lows, level, macd)
    segments = _unique_segments_by_sx(pens)
    edges = _build_edges(segments)
    _calc_segment_macd(segments, pens)
    return pens, segments, edges


def _calc_segment_macd(segments: Sequence[SegmentNode], pens: Sequence[PenNode]) -> None:
    """按笔汇总线段的 MACD 面积族指标。"""
    pen_lookup = {pen.id: pen for pen in pens}
    for segment in segments:
        pen_nodes = [pen_lookup[pid] for pid in segment.pens if pid in pen_lookup]
        if not pen_nodes:
            continue
        area_pos = sum(pen.macd_area_pos for pen in pen_nodes)
        area_neg = sum(pen.macd_area_neg for pen in pen_nodes)
        area_abs = sum(pen.macd_area_abs for pen in pen_nodes)
        area_dir = sum(pen.macd_area_net for pen in pen_nodes)
        segment.macd_area_abs = area_abs
        segment.macd_area_dir = area_dir
        segment.macd_area_net = area_dir
        segment.macd_peak_pos = max(pen.macd_peak_pos for pen in pen_nodes)
        segment.macd_peak_neg = min(pen.macd_peak_neg for pen in pen_nodes)
        segment.macd_dens = macd_density(area_abs, max(segment.i1 - segment.i0 + 1, 1))
        price_high = max(pen.high for pen in pen_nodes)
        price_low = min(pen.low for pen in pen_nodes)
        segment.macd_eff_price = macd_efficiency(area_abs, price_high - price_low)
        if area_dir > 0:
            segment.trend_state = "up"  # type: ignore[assignment]
        elif area_dir < 0:
            segment.trend_state = "down"  # type: ignore[assignment]
        else:
            segment.trend_state = "range"  # type: ignore[assignment]


def _detect_zhongshu(segment: SegmentNode, pens: Sequence[PenNode]) -> None:
    """最小实现的中枢识别：至少三笔且存在重叠价带时记录价带信息。"""
    if len(pens) < 3:
        return
    overlap_high = min(pen.high for pen in pens)
    overlap_low = max(pen.low for pen in pens)
    if overlap_high <= overlap_low:
        return
    mid = (overlap_high + overlap_low) / 2.0
    span = overlap_high - overlap_low
    segment.zhongshu = {
        "zg": overlap_high,
        "zd": overlap_low,
        "zm": mid,
        "span": span,
    }


def _divergence_between(
    prev: SegmentNode,
    cur: SegmentNode,
    pen_lookup: Mapping[str, PenNode],
    r_seg: float = 0.85,
) -> Divergence:
    """面积版段背驰：相邻同向段价格创新且面积衰减则记为趋势背驰。"""
    if prev.trend_state != cur.trend_state or prev.trend_state not in ("up", "down"):
        return "none"

    prev_pens = [pen_lookup.get(pid) for pid in prev.pens]
    cur_pens = [pen_lookup.get(pid) for pid in cur.pens]
    if any(p is None for p in prev_pens + cur_pens):
        return "none"

    prev_high = max(pen.high for pen in prev_pens if pen)
    prev_low = min(pen.low for pen in prev_pens if pen)
    cur_high = max(pen.high for pen in cur_pens if pen)
    cur_low = min(pen.low for pen in cur_pens if pen)

    if prev.trend_state == "up":
        if prev.macd_area_dir <= 0:
            return "none"
        price_new_high = cur_high >= prev_high
        area_decay = cur.macd_area_dir < r_seg * prev.macd_area_dir
        return "trend_div" if price_new_high and area_decay else "none"

    if prev.macd_area_dir >= 0:
        return "none"
    price_new_low = cur_low <= prev_low
    area_decay = abs(cur.macd_area_dir) < r_seg * abs(prev.macd_area_dir)
    return "trend_div" if price_new_low and area_decay else "none"


def build_multi_levels(
    level_bars: Dict[Level, Dict[str, Sequence[float]]],
    r_seg: float = 0.85,
) -> RSG:
    """多级别 RSG 构建：串联笔、线段、中枢、背驰与趋势节点。"""
    if not level_bars:
        raise ValueError("level_bars 不能为空。")

    level_order = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"]

    def _level_sort_key(lv: Level) -> tuple[int, str]:
        try:
            return (level_order.index(lv), lv)
        except ValueError:
            return (len(level_order), lv)

    levels_sorted = sorted(level_bars.keys(), key=_level_sort_key)

    symbol = "unknown"
    for data in level_bars.values():
        symbol = str(data.get("symbol", symbol))

    rsg = RSG(symbol=symbol, levels=list(levels_sorted))
    level_pen_ids: Dict[Level, List[str]] = {}
    level_seg_ids: Dict[Level, List[str]] = {}
    level_segments: Dict[Level, List[SegmentNode]] = {}
    cfg = Config()

    for level in levels_sorted:
        series = level_bars[level]
        closes = list(series.get("close", []))
        highs = list(series.get("high", []))
        lows = list(series.get("low", []))
        macd_hist = list(series.get("macd", []))

        if not (len(closes) == len(highs) == len(lows) == len(macd_hist)):
            raise ValueError(f"级别 {level} 的行情与 MACD 序列长度不一致。")

        bars = [
            {"close": c, "high": h, "low": l}
            for c, h, l in zip(closes, highs, lows)
        ]

        pens, segs, edges = build_level_pens_segments(bars, level, macd_hist)
        pen_lookup = {pen.id: pen for pen in pens}

        for seg in segs:
            seg_pens = [pen_lookup[pid] for pid in seg.pens if pid in pen_lookup]
            _detect_zhongshu(seg, seg_pens)
            tag_mmd_segment(seg)

        apply_strict_mmd_on_segments(segs, cfg.mmd_strict)
        apply_formal_mmd_on_segments(segs, cfg.mmd_strict)

        for idx in range(1, len(segs)):
            segs[idx].divergence = _divergence_between(
                segs[idx - 1], segs[idx], pen_lookup, r_seg=r_seg
            )

        for pen in pens:
            rsg.pens[pen.id] = pen
        for seg in segs:
            rsg.segments[seg.id] = seg
        rsg.edges.extend(edges)

        level_pen_ids[level] = [pen.id for pen in pens]
        level_seg_ids[level] = [seg.id for seg in segs]
        level_segments[level] = list(segs)

    def _edge(parent_id: str, child_id: str, low: Level, high: Level) -> None:
        rsg.edges.append(
            {"parent": parent_id, "child": child_id, "rel": "contains", "lv": (low, high)}
        )

    for idx in range(len(levels_sorted) - 1):
        low_level = levels_sorted[idx]
        high_level = levels_sorted[idx + 1]
        for sid_low in level_seg_ids.get(low_level, []):
            seg_low = rsg.segments[sid_low]
            for sid_high in level_seg_ids.get(high_level, []):
                seg_high = rsg.segments[sid_high]
                if seg_low.i0 >= seg_high.i0 and seg_low.i1 <= seg_high.i1:
                    _edge(seg_high.id, seg_low.id, low_level, high_level)

    for level in levels_sorted:
        seg_ids = level_seg_ids.get(level, [])
        segs = level_segments.get(level, [])
        zhongshu_count = sum(1 for seg in segs if seg.zhongshu)

        trend_state_candidates = [seg.trend_state for seg in segs if seg.trend_state in ("up", "down")]
        last_state = trend_state_candidates[-1] if trend_state_candidates else "range"
        if zhongshu_count >= 2:
            if last_state == "up":
                trend_type = "uptrend"
            elif last_state == "down":
                trend_type = "downtrend"
            else:
                trend_type = "range"
            confirmed = True
        else:
            trend_type = "range"
            confirmed = False

        total_abs = sum(seg.macd_area_abs for seg in segs)
        total_dir = sum(seg.macd_area_dir for seg in segs)
        total_span = sum(max(seg.i1 - seg.i0 + 1, 1) for seg in segs)
        peak_pos = max((seg.macd_peak_pos for seg in segs), default=0.0)
        peak_neg = min((seg.macd_peak_neg for seg in segs), default=0.0)

        pen_ids = level_pen_ids.get(level, [])
        price_high = max((rsg.pens[pid].high for pid in pen_ids), default=0.0)
        price_low = min((rsg.pens[pid].low for pid in pen_ids), default=0.0)

        trend_id = f"trend_{level}_0"
        trend_node = TrendNode(
            id=trend_id,
            level=level,
            segments=seg_ids,
            trend_type=trend_type,
            confirmed=confirmed,
            macd_area_dir=total_dir,
            macd_area_abs=total_abs,
            macd_area_net=total_dir,
            macd_peak_pos=peak_pos,
            macd_peak_neg=peak_neg,
            macd_dens=macd_density(total_abs, total_span if total_span else 1),
            macd_eff_price=macd_efficiency(total_abs, price_high - price_low),
        )
        rsg.trends[trend_id] = trend_node
        for seg_id in seg_ids:
            rsg.edges.append(
                {
                    "parent": trend_id,
                    "child": seg_id,
                    "rel": "trend_segment",
                    "lv": (level, level),
                }
            )

    rsg.build_info = {
        "version": "mvp-0.2",
        "r_seg": r_seg,
        "levels": list(levels_sorted),
    }
    return rsg
