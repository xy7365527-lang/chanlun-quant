from __future__ import annotations

from typing import List

from chanlun_quant.core.kline import normalize
from chanlun_quant.types import Bar, Fractal


def is_top_fractal(prev: Bar, mid: Bar, nxt: Bar) -> bool:
    return (mid.high > prev.high and mid.high > nxt.high) and (mid.low > prev.low and mid.low > nxt.low)


def is_bottom_fractal(prev: Bar, mid: Bar, nxt: Bar) -> bool:
    return (mid.low < prev.low and mid.low < nxt.low) and (mid.high < prev.high and mid.high < nxt.high)


def detect_fractals(bars: List[Bar]) -> List[Fractal]:
    """Detect raw fractals without normalization (assume bars已做去包含处理)."""
    res: List[Fractal] = []
    if len(bars) < 3:
        return res
    for i in range(1, len(bars) - 1):
        prev, mid, nxt = bars[i - 1], bars[i], bars[i + 1]
        if is_top_fractal(prev, mid, nxt):
            res.append(Fractal(type="top", index=i, price=mid.high, bar_index=mid.index, level=mid.level))
        elif is_bottom_fractal(prev, mid, nxt):
            res.append(Fractal(type="bottom", index=i, price=mid.low, bar_index=mid.index, level=mid.level))
    return res


def detect_on_normalized(bars: List[Bar]) -> List[Fractal]:
    """Normalize first (merge containment), then detect."""
    norm = normalize(bars)
    return detect_fractals(norm)
