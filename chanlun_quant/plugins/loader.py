from __future__ import annotations

from importlib import import_module
from typing import Any, Tuple, Type


def _split_path(path: str) -> Tuple[str, str]:
    if not path:
        raise ValueError("path cannot be empty")
    if ":" in path:
        module_path, class_name = path.split(":", 1)
    else:
        parts = path.split(".")
        if len(parts) < 2:
            raise ValueError(f"invalid path '{path}', expected module and class")
        module_path, class_name = ".".join(parts[:-1]), parts[-1]
    return module_path, class_name


def load_class(path: str) -> Type[Any]:
    module_path, class_name = _split_path(path)
    module = import_module(module_path)
    try:
        return getattr(module, class_name)
    except AttributeError as exc:  # pragma: no cover - defensive
        raise ImportError(f"class '{class_name}' not found in module '{module_path}'") from exc


def instantiate(path: str, **kwargs: Any) -> Any:
    cls = load_class(path)
    return cls(**kwargs)


__all__ = ["instantiate", "load_class"]

