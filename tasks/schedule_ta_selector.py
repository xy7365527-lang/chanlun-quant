# -*- coding: utf-8 -*-
"""
Simple scheduler to run TA_MA_Selector once per trading day after market close.
This script is a lightweight example; integrate with your production scheduler as needed.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import pytz

from examples.wire_ta_selector import parse_args as parse_wire_args, run_once


def _now_et() -> datetime:
    return datetime.now(pytz.timezone("US/Eastern"))


def main() -> None:
    args = parse_wire_args()
    output_dir = Path("outputs/orders")
    output_dir.mkdir(parents=True, exist_ok=True)
    last_run_date = None

    while True:
        current = _now_et()
        date_str = current.strftime("%Y-%m-%d")
        if current.hour == 16 and current.minute >= 10 and last_run_date != date_str:
            result = run_once(args)
            payload = {
                "as_of": date_str,
                "symbols": result.get("symbols", []),
                "meta": result.get("meta", {}),
                "table": result.get("data").to_dict(orient="records") if result.get("data") is not None else [],
            }
            path = output_dir / f"ta_selector_orders_{date_str}.json"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Wrote {path}")
            last_run_date = date_str
            time.sleep(60 * 50)  # Skip remainder of the hour
        time.sleep(30)


if __name__ == "__main__":
    main()
