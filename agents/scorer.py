from __future__ import annotations

from typing import List

from ..features.segment_index import SegmentIndex
from .evidence import score_with_evidence
from .evidence_loader import apply_calibration
from .signal import Signal


def score_signals(signals: List[Signal], seg_idx: SegmentIndex) -> List[Signal]:
    calibrated: List[Signal] = []
    for signal in signals:
        scored = score_with_evidence(signal, seg_idx)
        tags = scored.tags or []
        features = {
            "conf": scored.confidence,
            "str": scored.strength,
            "mmd1": 1 if any(t.startswith("1") for t in tags) else 0,
            "mmd2": 1 if any(t.startswith("2") for t in tags) else 0,
            "mmd3": 1 if any(t.startswith("3sell") or t.startswith("3buy") for t in tags) else 0,
            "mmd3w": 1 if any("3weak" in t for t in tags) else 0,
        }
        calibrated_conf, calibrated_strength = apply_calibration(scored.confidence, scored.strength, features)
        scored.confidence = calibrated_conf
        scored.strength = calibrated_strength
        calibrated.append(scored)
    return calibrated
