from __future__ import annotations

import csv
import json
import math
import os
from typing import Dict, List, Tuple

FEATURES: Tuple[str, ...] = ("conf", "str", "mmd1", "mmd2", "mmd3", "mmd3w")


def _sigmoid(x: float) -> float:
    x = max(-20.0, min(20.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def fit_logistic(csv_path: str, out_json: str, lr: float = 0.05, epoch: int = 8) -> str:
    samples: List[List[float]] = []
    targets: List[int] = []

    with open(csv_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            samples.append([float(row[feat]) for feat in FEATURES])
            targets.append(int(row["target"]))

    if not samples:
        weights = [0.2, 0.2, 0.05, 0.08, 0.12, 0.04]
        bias = -0.5
    else:
        weights = [0.0] * len(FEATURES)
        bias = 0.0
        for _ in range(epoch):
            for vec, label in zip(samples, targets):
                z = sum(w * x for w, x in zip(weights, vec)) + bias
                pred = _sigmoid(z)
                grad = pred - label
                for idx in range(len(weights)):
                    weights[idx] -= lr * grad * vec[idx]
                bias -= lr * grad

    payload: Dict[str, object] = {
        "bias": bias,
        "weights": {name: value for name, value in zip(FEATURES, weights)},
    }

    os.makedirs(os.path.dirname(out_json) or ".", exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    return out_json
