from __future__ import annotations

from typing import List, Set

from ..agents.signal import Signal
from ..config import SynergyCfg
from ..core.envelope import Envelope
from ..features.segment_index import SegmentIndex


def _segment_refs(refs: List[str]) -> Set[str]:
    return {ref for ref in (refs or []) if ref.startswith("seg_")}


def _has_pen_ref(refs: List[str]) -> bool:
    return any(ref.startswith("pen_") for ref in (refs or []))


def resolve_conflicts(
    signals: List[Signal],
    seg_idx: SegmentIndex,
    envelope: Envelope,
    cfg: SynergyCfg,
) -> List[Signal]:
    if not signals:
        return []

    drops: Set[int] = set()

    # 1) Segment divergence sell takes priority over pen buys within the same window.
    if cfg.seg_div_sell_suppress_pen:
        divergence_windows = []
        for signal in signals:
            if signal.kind != "sell":
                continue
            seg_refs = _segment_refs(signal.refs or [])
            if not seg_refs:
                continue
            if not any(method in (signal.methods or []) for method in ("divergence", "mmd")):
                continue
            for seg_id in seg_refs:
                segment = seg_idx.rsg.segments.get(seg_id)
                if segment:
                    divergence_windows.append((segment.i0, segment.i1))
        if divergence_windows:
            for idx, signal in enumerate(signals):
                if signal.kind != "buy" or not _has_pen_ref(signal.refs or []):
                    continue
                for ref in signal.refs or []:
                    pen = seg_idx.rsg.pens.get(ref)
                    if not pen:
                        continue
                    if any(window[0] <= pen.i0 and pen.i1 <= window[1] for window in divergence_windows):
                        drops.add(idx)
                        break

    # 2) Prefer segment signals when they conflict with pen signals at the same level.
    if cfg.prefer_segment_when_conflict:
        for i, sig_i in enumerate(signals):
            if i in drops:
                continue
            for j, sig_j in enumerate(signals):
                if j <= i or j in drops:
                    continue
                if sig_i.level != sig_j.level or sig_i.kind == sig_j.kind:
                    continue
                seg_i = bool(_segment_refs(sig_i.refs or []))
                seg_j = bool(_segment_refs(sig_j.refs or []))
                pen_i = _has_pen_ref(sig_i.refs or [])
                pen_j = _has_pen_ref(sig_j.refs or [])
                if seg_i and pen_j:
                    drops.add(j)
                elif seg_j and pen_i:
                    drops.add(i)

    # 3) Respect envelope net direction unless the action comes from higher-level segments.
    if cfg.enforce_net_direction and envelope.net_direction in ("long", "short"):
        for idx, signal in enumerate(signals):
            if idx in drops:
                continue
            seg_refs = _segment_refs(signal.refs or [])
            if envelope.net_direction == "long" and signal.kind == "sell" and not seg_refs:
                drops.add(idx)
            elif envelope.net_direction == "short" and signal.kind == "buy" and not seg_refs:
                drops.add(idx)

    return [signal for idx, signal in enumerate(signals) if idx not in drops]
