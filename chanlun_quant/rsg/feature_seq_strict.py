from __future__ import annotations

from typing import List

from .schema import Level, PenNode, SegmentNode


def strict_unique_policy(
    pens: List[PenNode],
    level: Level,
    min_pens: int = 3,
    max_back: int = 8,
    flip_tol: float = 0.15,
) -> List[SegmentNode]:
    """
    更严格的唯一化策略：

    - 至少 min_pens 条笔才能形成线段；
    - 在最近 max_back 条笔窗口内检测方向翻转；
    - 覆盖度不足或力度对称差时，将段标记为 feature_unstable；
    - 返回的段仍按顺序覆盖全部笔序列，未唯一化时以标签提示后续模块。
    """

    results: List[SegmentNode] = []
    if not pens:
        return results

    window = max(max_back, min_pens)

    def _make_segment(sequence: List[PenNode], unstable: bool) -> SegmentNode:
        start = sequence[0].i0
        end = sequence[-1].i1
        feature_seq = ["S" if pen.direction == "up" else "X" for pen in sequence]
        high = max(pen.high for pen in sequence)
        low = min(pen.low for pen in sequence)
        seg = SegmentNode(
            id=f"seg_{level}_{len(results)}",
            level=level,
            i0=start,
            i1=end,
            pens=[pen.id for pen in sequence],
            feature_seq=feature_seq,
            trend_state="up" if sequence[-1].direction == "up" else "down",
            high=float(high),
            low=float(low),
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
        )
        if unstable:
            seg.tags.append("feature_unstable")
        return seg

    buffer: List[PenNode] = []
    for pen in pens:
        buffer.append(pen)
        if len(buffer) < min_pens:
            continue
        if len(buffer) == 1:
            continue

        last = buffer[-1]
        prev = buffer[-2]
        flip = last.direction != prev.direction
        if not flip:
            continue

        recent = buffer[-window:]
        hi = max(p.high for p in recent)
        lo = min(p.low for p in recent)
        span = max(last.high, buffer[0].high) - min(last.low, buffer[0].low)
        cover_ok = True
        if span > 0:
            cover_ok = (hi - lo) >= (1.0 - flip_tol) * span

        results.append(_make_segment(buffer[:], unstable=not cover_ok))
        buffer = [pen]

    if buffer and len(buffer) >= min_pens:
        results.append(_make_segment(buffer, unstable=True))

    return results

