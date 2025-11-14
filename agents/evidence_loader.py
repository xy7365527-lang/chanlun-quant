from __future__ import annotations

import json
import os
from typing import Dict, Tuple

_calib: Dict[str, object] | None = None


def load_calibration(path: str | None) -> None:
    """Load calibration weights from a JSON file if present."""
    global _calib
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            _calib = json.load(fh)
    else:
        _calib = None


def apply_calibration(conf: float, strength: float, features: Dict[str, float]) -> Tuple[float, float]:
    """
    Apply a lightweight logistic calibration over the `(confidence, strength)` pair.

    The calibration is capped to keep adjustments within a small ±0.2 band to avoid
    destabilising downstream sizing heuristics.
    """
    if not _calib:
        return conf, strength

    weights = _calib.get("weights", {}) if isinstance(_calib, dict) else {}
    bias = float(_calib.get("bias", 0.0)) if isinstance(_calib, dict) else 0.0
    z = bias
    for key, value in weights.items():
        z += float(value) * float(features.get(key, 0.0))

    delta = max(-0.2, min(0.2, z))
    adjusted_conf = max(0.0, min(1.0, conf + delta * 0.5))
    adjusted_strength = max(0.0, min(1.0, strength + delta * 0.5))
    return adjusted_conf, adjusted_strength
