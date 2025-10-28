from chanlun_quant.rsg.build import build_multi_levels
from chanlun_quant.features.segment_index import SegmentIndex
from chanlun_quant.selector.level_selector import post_validate_levels


class DummyFeed:
    def get_bars(self, symbol, level):
        n = 140
        close = [i * 0.1 for i in range(n)]
        high = [c + 0.05 for c in close]
        low = [c - 0.05 for c in close]
        macd = [((i % 10) - 5) / 10 for i in range(n)]
        return {"close": close, "high": high, "low": low, "macd": macd}


def test_strict_mmd_and_bridge():
    feed = DummyFeed()
    level_bars = {
        "M15": feed.get_bars("X", "M15"),
        "H1": feed.get_bars("X", "H1"),
        "D1": feed.get_bars("X", "D1"),
    }
    rsg = build_multi_levels(level_bars)
    seg_idx = SegmentIndex(rsg)

    assert any(seg.mmds for seg in rsg.segments.values())

    levels = post_validate_levels(
        rsg,
        seg_idx,
        ["M15", "H1", "D1"],
        candidates=["M5", "M15", "H1", "H4", "D1", "W1"],
    )
    assert isinstance(levels, list)
    assert len(levels) >= 3
