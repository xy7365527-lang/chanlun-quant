"""Chanlun Quant package initialization."""

import importlib as _importlib
import os
import sys as _sys

_PKG_DIR = os.path.dirname(__file__)
__path__ = [_PKG_DIR, os.path.join(_PKG_DIR, "chanlun_quant")]

_LLM_ENV_DEFAULTS = {
    "CLQ_LLM_PROVIDER": "siliconflow",
    "CLQ_LLM_API_BASE": "https://api.siliconflow.cn/v1",
    "CLQ_LLM_API_KEY": "sk-suxnurbgywafwqcvfkhbpodtozjfwektnbimlwtfgyxkqgqm",
    "CLQ_LLM_MODEL": "deepseek-ai/DeepSeek-V3.2-Exp",
}

for _var, _value in _LLM_ENV_DEFAULTS.items():
    os.environ.setdefault(_var, _value)

del _LLM_ENV_DEFAULTS, _var, _value

_nested = _importlib.import_module(".chanlun_quant", __name__)
_sys.modules[f"{__name__}.chanlun_quant"] = _nested

ai = _nested.ai
analysis = _nested.analysis
broker = _nested.broker
core = _nested.core
datafeed = _nested.datafeed
features = _nested.features
integration = _nested.integration
plugins = _nested.plugins
risk = _nested.risk
runtime = _nested.runtime
strategy = _nested.strategy
Config = _nested.Config

for _name in ("ai", "analysis", "broker", "core", "datafeed", "features", "integration", "plugins", "risk", "runtime", "strategy"):
    _sys.modules[f"{__name__}.{_name}"] = globals()[_name]

__all__ = ["ai", "analysis", "broker", "core", "datafeed", "features", "integration", "plugins", "risk", "runtime", "strategy", "Config"]

