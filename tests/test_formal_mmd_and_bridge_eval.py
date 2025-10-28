from chanlun_quant.config import Config
from chanlun_quant.core.envelope import Envelope
from chanlun_quant.fugue.level_coordinator import Plan, Proposal, sanitize_and_clip
from chanlun_quant.features.segment_index import SegmentIndex
from chanlun_quant.rsg.build import build_multi_levels
from chanlun_quant.selector.level_selector import post_validate_levels


class DummyFeed:
    def get_bars(self, symbol, level):
        n = 140
        close = [i * 0.1 for i in range(n)]
        high = [c + 0.05 for c in close]
        low = [c - 0.05 for c in close]
        macd = [((i % 10) - 5) / 10 for i in range(n)]
        return {"close": close, "high": high, "low": low, "macd": macd}


def test_mmd_direction_and_bridge():
    feed = DummyFeed()
    level_bars = {
        "M15": feed.get_bars("X", "M15"),
        "H1": feed.get_bars("X", "H1"),
        "D1": feed.get_bars("X", "D1"),
    }
    rsg = build_multi_levels(level_bars)
    seg_idx = SegmentIndex(rsg)
    cfg = Config()

    levels = post_validate_levels(
        rsg,
        seg_idx,
        ["M15", "H1", "D1"],
        candidates=["M5", "M15", "H1", "H4", "D1", "W1"],
        nest_cfg=cfg.nesting_cfg,
    )
    assert isinstance(levels, list) and len(levels) >= 3

    any_seg = next(iter(seg_idx.rsg.segments.values()), None)
    if any_seg:
        any_seg.mmds = ["3sell"]
        plan = Plan(
            proposals=[
                Proposal(
                    bucket="segment",
                    action="BUY",
                    size_delta=10.0,
                    refs=[any_seg.id],
                    methods=["mmd"],
                )
            ]
        )
        env = Envelope(net_direction="long", child_max_ratio=0.35)
        safe = sanitize_and_clip(
            plan,
            env,
            seg_idx,
            risk_ctx={"core_qty": 1000, "guard_strict": True},
        )
        assert len(safe.proposals) == 0 or all(proposal.action != "BUY" for proposal in safe.proposals)
