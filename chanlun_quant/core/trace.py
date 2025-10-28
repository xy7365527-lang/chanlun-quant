from __future__ import annotations

import json
import os
import time
from typing import Any, Dict


class TraceLog:
    def __init__(self, out_dir: str = "runs/trace") -> None:
        os.makedirs(out_dir, exist_ok=True)
        self.path = os.path.join(out_dir, f"trace_{int(time.time())}.jsonl")

    def write(self, payload: Dict[str, Any]) -> None:
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

