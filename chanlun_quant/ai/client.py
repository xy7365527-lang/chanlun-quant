from __future__ import annotations

import json
import time
import urllib.request
from typing import Any, Dict, Optional


class JsonLLMClient:
    """Unified JSON LLM client with basic HTTP POST + retry logic."""

    def __init__(self, endpoint: str, api_key: Optional[str] = None, timeout: float = 15.0, max_retries: int = 2) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    def ask_json(self, prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"prompt": prompt, "schema": schema}
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(self.endpoint, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    text = resp.read().decode("utf-8")
                obj = json.loads(text)
                if not isinstance(obj, dict) or "proposals" not in obj:
                    raise ValueError("Invalid JSON: missing 'proposals'")
                if not isinstance(obj["proposals"], list):
                    raise ValueError("Invalid JSON: proposals must be list")
                return obj
            except Exception:
                if attempt >= self.max_retries:
                    raise
                time.sleep(1.5 * (2 ** attempt))
        raise RuntimeError("LLM request failed after retries")
