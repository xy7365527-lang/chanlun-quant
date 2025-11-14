from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


MetricMap = Mapping[str, float]

DEFAULT_METRICS: Dict[str, float] = {
    "annual_return": 0.03,
    "max_drawdown": 0.02,
    "win_rate": 0.05,
    "trade_count": 1.0,
    "avg_trade_pnl": 0.02,
}


@dataclass
class Comparison:
    metric: str
    legacy: Optional[float]
    quant: Optional[float]
    diff: Optional[float]
    tolerance: float
    passed: bool


def _flatten_items(obj: Any, prefix: str = "") -> Iterable[Tuple[str, Any]]:
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            new_prefix = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten_items(value, new_prefix)
    elif isinstance(obj, (list, tuple)):
        for idx, value in enumerate(obj):
            new_prefix = f"{prefix}[{idx}]"
            yield from _flatten_items(value, new_prefix)
    else:
        yield prefix, obj


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_metric(data: Mapping[str, Any], metric: str) -> Optional[float]:
    metric_lower = metric.lower()
    best_match: Optional[float] = None
    for key, value in _flatten_items(data):
        if not key:
            continue
        key_lower = key.lower()
        if metric_lower in key_lower.split(".") or key_lower.endswith(metric_lower):
            candidate = _to_float(value)
            if candidate is not None:
                best_match = candidate
                break
    return best_match


def load_struct(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix in {".json"}:
        return json.loads(path.read_text(encoding="utf-8"))
    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML 未安装，无法解析 YAML 文件")
        with path.open("r", encoding="utf-8") as fp:
            return yaml.safe_load(fp)
    if suffix in {".txt"}:
        # 支持简单的 key=value 格式
        result: Dict[str, Any] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            result[key] = _to_float(value) or value
        return result
    raise ValueError(f"不支持的文件类型: {path}")


def compare_metrics(
    legacy_data: Mapping[str, Any],
    quant_data: Mapping[str, Any],
    metrics: MetricMap,
) -> List[Comparison]:
    comparisons: List[Comparison] = []
    for metric, tolerance in metrics.items():
        legacy_val = extract_metric(legacy_data, metric)
        quant_val = extract_metric(quant_data, metric)
        if legacy_val is None or quant_val is None:
            comparisons.append(
                Comparison(
                    metric=metric,
                    legacy=legacy_val,
                    quant=quant_val,
                    diff=None,
                    tolerance=tolerance,
                    passed=False,
                )
            )
            continue
        diff = abs(legacy_val - quant_val)
        passed = diff <= tolerance
        comparisons.append(
            Comparison(
                metric=metric,
                legacy=legacy_val,
                quant=quant_val,
                diff=diff,
                tolerance=tolerance,
                passed=passed,
            )
        )
    return comparisons


def load_config(path: Optional[Path]) -> Dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        raise FileNotFoundError(path)
    if yaml is None:
        raise RuntimeError("PyYAML 未安装，无法解析配置文件")
    with path.open("r", encoding="utf-8") as fp:
        return yaml.safe_load(fp)


def format_markdown_report(name: str, comparisons: List[Comparison]) -> str:
    header = f"### {name}\n\n| 指标 | Legacy | Quant | 差值 | 容差 | 结果 |\n|------|--------|-------|------|------|------|\n"
    rows = []
    for item in comparisons:
        legacy_text = "—" if item.legacy is None else f"{item.legacy:.6f}"
        quant_text = "—" if item.quant is None else f"{item.quant:.6f}"
        diff_text = "—" if item.diff is None else f"{item.diff:.6f}"
        status = "通过" if item.passed else "超限"
        rows.append(f"| {item.metric} | {legacy_text} | {quant_text} | {diff_text} | {item.tolerance:.6f} | {status} |")
    return header + "\n".join(rows) + "\n"


def determine_exit_code(comparisons: List[Comparison]) -> int:
    if any(not item.passed for item in comparisons):
        return 1
    return 0


def run_single_compare(
    legacy_path: Path,
    quant_path: Path,
    metrics: MetricMap,
    name: str = "compare",
) -> Tuple[List[Comparison], str]:
    legacy_data = load_struct(legacy_path)
    quant_data = load_struct(quant_path)
    comparisons = compare_metrics(legacy_data, quant_data, metrics)
    report = format_markdown_report(name, comparisons)
    return comparisons, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="比较旧版与新版回测指标差异")
    parser.add_argument("--legacy", help="Legacy 回测结果文件 (JSON/YAML/TXT)")
    parser.add_argument("--quant", help="新版回测结果文件 (JSON/YAML/TXT)")
    parser.add_argument("--config", default="configs/legacy_compare.yaml", help="阈值/批量对照配置文件")
    parser.add_argument("--output", help="输出报告文件，支持 .md/.json，默认打印到 stdout")
    parser.add_argument("--metrics", help="JSON 字符串覆写指标阈值，如 '{\"annual_return\":0.02}'")
    parser.add_argument("--all", action="store_true", help="使用配置文件中的所有 cases 批量比较")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config_path = Path(args.config) if args.config else None
    config = load_config(config_path) if config_path else {}

    metrics: Dict[str, float] = dict(DEFAULT_METRICS)
    if "metrics" in config:
        metrics.update({k: float(v) for k, v in config["metrics"].items()})
    if args.metrics:
        metrics.update({k: float(v) for k, v in json.loads(args.metrics).items()})

    reports: List[str] = []
    exit_codes: List[int] = []
    aggregate: Dict[str, Any] = {"comparisons": []}

    def _record(name: str, comparisons: List[Comparison], report: str) -> None:
        reports.append(report)
        aggregate["comparisons"].append(
            {
                "name": name,
                "results": [
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
        )
        exit_codes.append(determine_exit_code(comparisons))

    if args.all:
        cases = config.get("cases", [])
        if not cases:
            raise RuntimeError("配置文件中未找到 cases，无法批量执行")
        for case in cases:
            name = case.get("name", "case")
            legacy_path = Path(case["legacy"])
            quant_path = Path(case["quant"])
            comps, report = run_single_compare(legacy_path, quant_path, metrics, name=name)
            _record(name, comps, report)
    else:
        if not args.legacy or not args.quant:
            raise RuntimeError("请提供 --legacy 与 --quant 文件或使用 --all")
        comps, report = run_single_compare(Path(args.legacy), Path(args.quant), metrics, name="compare")
        _record("compare", comps, report)

    combined_report = "\n".join(reports)

    if args.output:
        output_path = Path(args.output)
        if output_path.suffix.lower() == ".json":
            output_path.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            output_path.write_text(combined_report, encoding="utf-8")
    else:
        print(combined_report)

    sys.exit(max(exit_codes) if exit_codes else 0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(130)

