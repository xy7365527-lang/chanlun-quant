"""Chanlun Quant package initialization."""

import os

_LLM_ENV_DEFAULTS = {
    "CLQ_LLM_PROVIDER": "siliconflow",
    "CLQ_LLM_API_BASE": "https://api.siliconflow.cn/v1",
    "CLQ_LLM_API_KEY": "sk-suxnurbgywafwqcvfkhbpodtozjfwektnbimlwtfgyxkqgqm",
    "CLQ_LLM_MODEL": "deepseek-ai/DeepSeek-V3.2-Exp",
}

# Populate ChanLLM environment defaults unless the caller overrides them ahead of import.
for _var, _value in _LLM_ENV_DEFAULTS.items():
    os.environ.setdefault(_var, _value)

del _LLM_ENV_DEFAULTS, _var, _value
