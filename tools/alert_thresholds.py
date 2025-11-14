from __future__ import annotations

import argparse
import json
import sys

from .monitor_trace import summarize_trace


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True, help="Path to trace.jsonl file.")
    parser.add_argument("--max_issues", type=int, default=20, help="Maximum allowed structure issues.")
    parser.add_argument("--max_jump", type=float, default=0.15, help="Maximum allowed envelope jump.")
    args = parser.parse_args()

    report = summarize_trace(args.trace)
    issues = int(report.get("structure_issues", 0))
    jump = float(report.get("envelope_jump_max", 0.0))

    payload = {"issues": issues, "jump": jump}
    print(json.dumps(payload, ensure_ascii=False))

    if issues > args.max_issues or jump > args.max_jump:
        sys.exit(2)


if __name__ == "__main__":
    main()
