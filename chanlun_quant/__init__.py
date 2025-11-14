"""chanlun_quant 包的轻量初始化模块。"""

import importlib as _importlib
import os as _os
import sys as _sys

_PKG_DIR = _os.path.dirname(__file__)
__path__ = [_PKG_DIR]

_EXPORT_MODULES = [
    "ai",
    "analysis",
    "broker",
    "core",
    "datafeed",
    "features",
    "integration",
    "plugins",
    "risk",
    "runtime",
    "strategy",
]

for _name in _EXPORT_MODULES:
    _module = _importlib.import_module(f".{_name}", __name__)
    globals()[_name] = _module
    _sys.modules[f"{__name__}.{_name}"] = _module

_config_module = _importlib.import_module(".config", __name__)
Config = _config_module.Config

_types_module = _importlib.import_module(".types", __name__)
globals().update({k: v for k, v in _types_module.__dict__.items() if not k.startswith("_")})

__all__ = _EXPORT_MODULES + ["Config"]
__all__ += [name for name in globals().keys() if not name.startswith("_")]
__all__ = list(dict.fromkeys(__all__))

