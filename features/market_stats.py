from __future__ import annotations

import math
from typing import Dict, List

from ..rsg.schema import Level, RSG


def atr(highs: List[float], lows: List[float], closes: List[float], n: int = 14) -> float:
    n = min(n, len(closes) - 1) if len(closes) >= 2 else 0
    if n <= 0:
        return 0.0
    trs: List[float] = []
    for i in range(-n, 0):
        hi = highs[i]
        lo = lows[i]
        prev_close = closes[i - 1]
        tr = max(hi - lo, abs(hi - prev_close), abs(lo - prev_close))
        trs.append(tr)
    return sum(trs) / len(trs)


def natr(highs: List[float], lows: List[float], closes: List[float], n: int = 14) -> float:
    avg_tr = atr(highs, lows, closes, n)
    last = closes[-1] if closes else 1.0
    return avg_tr / max(abs(last), 1e-12)


def density_pens_per_100bars(rsg: RSG, level: Level, bars_len: int) -> float:
    pens = [pen for pen in rsg.pens.values() if pen.level == level]
    if bars_len <= 0:
        return 0.0
    return (len(pens) / bars_len) * 100.0


def zhongshu_cover_ratio(rsg: RSG, level: Level, highs: List[float], lows: List[float]) -> float:
    segments = [seg for seg in rsg.segments.values() if seg.level == level and seg.zhongshu]
    if not segments:
        return 0.0
    recent_highs = highs[-200:] if highs else highs
    recent_lows = lows[-200:] if lows else lows
    if not recent_highs or not recent_lows:
        return 0.0
    span_price = max(recent_highs) - min(recent_lows)
    if not math.isfinite(span_price) or span_price <= 0:
        span_price = 1.0
    avg_span = 0.0
    count = 0
    for seg in segments:
        span = seg.zhongshu.get("span")
        if isinstance(span, (int, float)) and math.isfinite(span):
            avg_span += float(span)
            count += 1
    if count == 0:
        return 0.0
    avg_span /= count
    return avg_span / max(abs(span_price), 1e-12)
