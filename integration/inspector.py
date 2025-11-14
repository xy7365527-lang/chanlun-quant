from __future__ import annotations

import inspect
import json
from typing import Any, Dict

from chanlun_quant.config import Config
from chanlun_quant.plugins.loader import instantiate


def _maybe_kwargs(cfg: Config) -> dict:
    text = (cfg.external_kwargs_json or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        return {}


def _signature_table(obj: Any) -> Dict[str, str]:
    table: Dict[str, str] = {}
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            attr = getattr(obj, name)
        except Exception:
            continue
        if callable(attr):
            try:
                table[name] = str(inspect.signature(attr))
            except Exception:
                table[name] = "(callable)"
    return table


def inspect_external(cfg: Config) -> Dict[str, dict]:
    report: Dict[str, dict] = {}
    kwargs = _maybe_kwargs(cfg)

    def _try(path: str, key: str):
        if not path:
            report[key] = {"loaded": False, "reason": "empty path"}
            return None
        try:
            inst = instantiate(path, **kwargs)
            report[key] = {
                "loaded": True,
                "class": path,
                "methods": _signature_table(inst),
            }
            return inst
        except Exception as exc:
            report[key] = {"loaded": False, "class": path, "error": str(exc)}
            return None

    broker = _try(cfg.external_broker_class, "broker")
    llm = _try(cfg.external_llm_client_class, "llm")
    datafeed = _try(cfg.external_datafeed_class, "datafeed")

    if report.get("broker", {}).get("loaded"):
        methods = report["broker"]["methods"].keys()
        for candidate in ("place_order", "order", "send_order", "create_order", "trade"):
            if candidate in methods:
                report["broker"]["suggested_map"] = {"place_order": candidate}
                break

    if report.get("llm", {}).get("loaded"):
        methods = report["llm"]["methods"].keys()
        suggested = {}
        if "ask_json" in methods:
            suggested["ask_json"] = "ask_json"
        elif "chat" in methods:
            suggested["ask_json"] = "chat"
        if "ask_text" in methods:
            suggested["ask_text"] = "ask_text"
        report["llm"]["suggested_map"] = suggested or {"ask_json": "chat/parse_json"}

    if report.get("datafeed", {}).get("loaded"):
        methods = report["datafeed"]["methods"].keys()
        for candidate in ("get_bars", "fetch"):
            if candidate in methods:
                report["datafeed"]["suggested_map"] = {"get_bars": candidate}
                break

    return report
