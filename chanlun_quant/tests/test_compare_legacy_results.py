from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from script.compare_legacy_results import (
    Comparison,
    compare_metrics,
    run_single_compare,
)


def test_compare_metrics_pass_when_within_tolerance() -> None:
    metrics = {"annual_return": 0.05, "trade_count": 1}
    legacy = {"annual_return": 0.20, "trade_count": 40}
    quant = {"annual_return": 0.17, "trade_count": 40}
    comparisons = compare_metrics(legacy, quant, metrics)

    annual = next(item for item in comparisons if item.metric == "annual_return")
    assert annual.passed is True
    assert pytest.approx(0.03) == annual.diff

    trades = next(item for item in comparisons if item.metric == "trade_count")
    assert trades.passed is True
    assert trades.diff == 0


def test_compare_metrics_fail_when_missing_metric() -> None:
    metrics = {"win_rate": 0.05}
    legacy = {}
    quant = {"win_rate": 0.6}
    comparisons = compare_metrics(legacy, quant, metrics)
    assert len(comparisons) == 1
    assert comparisons[0].passed is False
    assert comparisons[0].legacy is None


def test_run_single_compare(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.json"
    quant_path = tmp_path / "quant.json"
    legacy_path.write_text(json.dumps({"annual_return": 0.2}), encoding="utf-8")
    quant_path.write_text(json.dumps({"annual_return": 0.18}), encoding="utf-8")

    comparisons, report = run_single_compare(
        legacy_path,
        quant_path,
        metrics={"annual_return": 0.05},
        name="unit",
    )
    assert isinstance(report, str) and "unit" in report
    assert comparisons[0].passed is True

