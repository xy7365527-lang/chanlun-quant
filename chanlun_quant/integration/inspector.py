from __future__ import annotations

import inspect
import json
from typing import Any, Dict

from chanlun_quant.config import Config
from chanlun_quant.plugins.loader import instantiate


def _maybe_kwargs(cfg: Config) -> Dict[str, Any]:
    raw = (cfg.external_kwargs_json or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


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
            except (TypeError, ValueError):
                table[name] = "(callable)"
    return table


def inspect_external(cfg: Config) -> Dict[str, Dict[str, Any]]:
    """Inspect user-provided integrations and suggest adapter mappings."""

    report: Dict[str, Dict[str, Any]] = {}
    kwargs = _maybe_kwargs(cfg)

    def _probe(path: str, key: str) -> Any:
        if not path:
            report[key] = {"loaded": False, "reason": "empty path"}
            return None
        try:
            instance = instantiate(path, **kwargs)
        except Exception as exc:  # pragma: no cover - depends on user env
            report[key] = {"loaded": False, "class": path, "error": str(exc)}
            return None
        report[key] = {
            "loaded": True,
            "class": path,
            "methods": _signature_table(instance),
        }
        return instance

    broker = _probe(cfg.external_broker_class, "broker")
    llm = _probe(cfg.external_llm_client_class, "llm")
    datafeed = _probe(cfg.external_datafeed_class, "datafeed")

    if report.get("broker", {}).get("loaded"):
        methods = report["broker"].get("methods", {})
        for candidate in ("place_order", "order", "send_order", "trade"):
            if candidate in methods:
                report["broker"]["suggested_map"] = {"place_order": candidate}
                break

    if report.get("llm", {}).get("loaded"):
        methods = report["llm"].get("methods", {})
        suggestions: Dict[str, str] = {}
        if "ask_json" in methods:
            suggestions["ask_json"] = "ask_json"
        elif "chat" in methods:
            suggestions["ask_json"] = "chat"
        if "ask_text" in methods:
            suggestions["ask_text"] = "ask_text"
        elif "chat" in methods and "ask_json" not in suggestions:
            suggestions["ask_text"] = "chat"
        if suggestions:
            report["llm"]["suggested_map"] = suggestions

    if report.get("datafeed", {}).get("loaded"):
        methods = report["datafeed"].get("methods", {})
        for candidate in ("get_bars", "fetch"):
            if candidate in methods:
                report["datafeed"]["suggested_map"] = {"get_bars": candidate}
                break

    return report


__all__ = ["inspect_external"]

