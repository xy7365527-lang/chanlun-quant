from __future__ import annotations

from importlib import import_module
from typing import Any, Tuple


def _split_path(path: str) -> Tuple[str, str]:
    if ":" in path:
        module, cls = path.split(":", 1)
    else:
        parts = path.split(".")
        module, cls = ".".join(parts[:-1]), parts[-1]
    return module, cls


def load_class(path: str):
    module_name, class_name = _split_path(path)
    module = import_module(module_name)
    return getattr(module, class_name)


def instantiate(path: str, **kwargs) -> Any:
    cls = load_class(path)
    return cls(**kwargs)
