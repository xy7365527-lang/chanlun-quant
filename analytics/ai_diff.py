from __future__ import annotations

from collections import Counter
from typing import Any, Dict


def plan_metrics(plan) -> Dict[str, Any]:
    buckets = Counter()
    actions = Counter()
    methods = Counter()
    tags = Counter()
    proposals = getattr(plan, "proposals", []) or []
    for proposal in proposals:
        buckets[proposal.bucket] += 1
        actions[proposal.action] += 1
        for method in proposal.methods or []:
            methods[method] += 1
            if method.startswith("mmd"):
                tags[method] += 1
    return {
        "count": len(proposals),
        "buckets": dict(buckets),
        "actions": dict(actions),
        "methods": dict(methods),
        "tags": dict(tags),
    }


def diff_metrics(base: Dict[str, Any], other: Dict[str, Any]) -> Dict[str, Any]:
    def delta(key: str) -> Dict[str, int]:
        result: Dict[str, int] = {}
        keys = set(base.get(key, {})) | set(other.get(key, {}))
        for name in keys:
            result[name] = other.get(key, {}).get(name, 0) - base.get(key, {}).get(name, 0)
        return result

    return {
        "count_delta": other.get("count", 0) - base.get("count", 0),
        "buckets_delta": delta("buckets"),
        "actions_delta": delta("actions"),
        "methods_delta": delta("methods"),
        "tags_delta": delta("tags"),
    }
