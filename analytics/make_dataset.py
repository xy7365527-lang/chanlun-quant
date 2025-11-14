from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict, Iterator, List


def _iter_jsonl(path: str) -> Iterator[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            try:
                record = json.loads(line)
            except Exception:
                continue
            if isinstance(record, dict):
                yield record


def build_dataset(trace_path: str, out_csv: str) -> str:
    """
    Build a lightweight classification dataset from trace events.

    Each sample pairs a scored signal snapshot with the next ledger update,
    labelling the signal as positive if the remaining_cost shrinks or the
    realised PnL increases.
    """
    rows: List[Dict[str, Any]] = []
    last_remaining: float | None = None
    last_realized: float | None = None
    buffered_signals: List[Dict[str, Any]] | None = None

    for record in _iter_jsonl(trace_path):
        phase = record.get("phase", "")
        if phase == "signals_scored":
            buffered_signals = record.get("signals", []) or []
        elif phase == "post_exec" and buffered_signals is not None:
            ledger = record.get("ledger", {}) or {}
            remaining = float(ledger.get("remaining_cost", 0.0))
            realized = float(ledger.get("realized_total", 0.0))

            target = 0
            if last_remaining is not None and remaining < last_remaining:
                target = 1
            if last_realized is not None and realized > last_realized:
                target = 1

            for signal in buffered_signals:
                tags = signal.get("tags") or []
                rows.append(
                    {
                        "kind": signal.get("kind"),
                        "level": signal.get("level"),
                        "conf": float(signal.get("confidence", 0.5)),
                        "str": float(signal.get("strength", 0.5)),
                        "mmd1": 1 if any(str(tag).startswith("1") for tag in tags) else 0,
                        "mmd2": 1 if any(str(tag).startswith("2") for tag in tags) else 0,
                        "mmd3": 1
                        if any(str(tag).startswith("3sell") or str(tag).startswith("3buy") for tag in tags)
                        else 0,
                        "mmd3w": 1 if any("3weak" in str(tag) for tag in tags) else 0,
                        "target": target,
                    }
                )

            buffered_signals = None
            last_remaining = remaining
            last_realized = realized

    os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["kind", "level", "conf", "str", "mmd1", "mmd2", "mmd3", "mmd3w", "target"],
        )
        writer.writeheader()
        writer.writerows(rows)

    return out_csv
