from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from script.compare_legacy_results import compare_metrics, format_markdown_report, load_struct


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="执行 legacy 对照回测差异检查")
    parser.add_argument("--config", default="configs/legacy_compare.yaml", help="对照配置文件")
    parser.add_argument("--output", default="reports/legacy_regression.md", help="输出报告文件 (.md/.json)")
    return parser.parse_args()


def load_cases(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def run_case(case: Dict[str, Any], metrics: Dict[str, float]) -> Dict[str, Any]:
    name = case.get("name", "case")
    legacy_data = load_struct(Path(case["legacy"]))
    quant_data = load_struct(Path(case["quant"]))
    comparisons = compare_metrics(legacy_data, quant_data, metrics)
    report = format_markdown_report(name, comparisons)
    passed = all(item.passed for item in comparisons)
    payload = {
        "name": name,
        "report": report,
        "passed": passed,
        "comparisons": [
            {
                "metric": item.metric,
                "legacy": item.legacy,
                "quant": item.quant,
                "diff": item.diff,
                "tolerance": item.tolerance,
                "passed": item.passed,
            }
            for item in comparisons
        ],
    }
    return payload


def persist_reports(reports: List[Dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".json":
        output.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        markdown = "\n".join(item["report"] for item in reports)
        output.write_text(markdown, encoding="utf-8")


def main() -> None:
    args = parse_args()
    config = load_cases(Path(args.config))
    metrics = {k: float(v) for k, v in config.get("metrics", {}).items()}
    reports: List[Dict[str, Any]] = []
    statuses: List[bool] = []
    for case in config.get("cases", []):
        payload = run_case(case, metrics)
        reports.append(payload)
        statuses.append(payload["passed"])
        print(payload["report"])  # 在控制台同步输出
    persist_reports(reports, Path(args.output))
    if not all(statuses):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
