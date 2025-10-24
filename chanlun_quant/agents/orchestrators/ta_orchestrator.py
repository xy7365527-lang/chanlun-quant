# -*- coding: utf-8 -*-
"""
TradingAgents orchestrator facade for chanlun-quant.

Responsibilities
----------------
- Create and keep a TradingAgents orchestrator instance using a configurable entrypoint.
- Provide configuration hooks for provider/model/tools/etc. via env, YAML, or direct kwargs.
- Expose a lightweight ask(prompt) wrapper whose output is normalized closer to JSON.

Notes for SiliconFlow + DeepSeek
--------------------------------
By default we treat SiliconFlow as an OpenAI-compatible endpoint:
- provider defaults to ``openai`` so that TradingAgentsGraph uses ChatOpenAI.
- api_base/api_key default to the SiliconFlow REST endpoint and provided key.
Override these via environment variables or YAML if you rotate keys or switch providers.
"""

from __future__ import annotations

import copy
import importlib
import inspect
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import yaml  # Optional: used when reading configuration from YAML files.
except Exception:  # noqa: W0703 - fall back gracefully if PyYAML is absent.
    yaml = None

logger = logging.getLogger(__name__)

# Automatically add external directory to Python path for TradingAgents
_module_dir = Path(__file__).parent.parent.parent.parent  # Navigate to project root
_external_dir = _module_dir / "external"
if _external_dir.exists() and str(_external_dir) not in sys.path:
    sys.path.insert(0, str(_external_dir))
    logger.info(f"Added {_external_dir} to Python path for TradingAgents")


# === Utility helpers ======================================================


def _load_obj(dotted_path: str) -> Callable[..., Any]:
    """
    Import "module.submodule:attr" lazily and return the referenced attribute.
    """
    if ":" not in dotted_path:
        raise ValueError(f"Invalid entrypoint (expect 'module:attr'): {dotted_path}")
    module_path, attr_name = dotted_path.split(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, attr_name)


def _ensure_json_obj(text_or_obj: Any) -> Any:
    """
    Convert orchestrator output into a JSON-friendly object when possible.
    - dict/list pass through;
    - string attempts json.loads with a { ... } fallback;
    - everything else returns original (AgentsAdapter will handle).
    """
    if isinstance(text_or_obj, (dict, list)):
        return text_or_obj
    if isinstance(text_or_obj, str):
        payload = text_or_obj.strip()
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except Exception:
            # Try to extract JSON object from response (simple approach without recursion)
            import re
            # Find the first complete JSON object (handles simple nesting)
            brace_count = 0
            start_idx = payload.find('{')
            if start_idx != -1:
                for i in range(start_idx, len(payload)):
                    if payload[i] == '{':
                        brace_count += 1
                    elif payload[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            try:
                                return json.loads(payload[start_idx:i+1])
                            except Exception:
                                break
            return text_or_obj
    return text_or_obj


# === Default JSON schema (can be overridden) ==============================

DEFAULT_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "analysis": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "score": {"type": "number"},
                    "recommendation": {"type": "string", "enum": ["买入", "观察", "忽略"]},
                    "reason": {"type": "string"},
                },
                "required": ["symbol", "score", "recommendation"],
                "additionalProperties": True,
            },
        },
        "top_picks": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 0,
            "maxItems": 2,
        },
    },
    "required": ["analysis", "top_picks"],
    "additionalProperties": False,
}


# === Configuration dataclass ==============================================


@dataclass
class TAConfig:
    """
    Full set of TradingAgents knobs we care about.
    """

    entrypoint: str = "trading_agents.tradingagents.graph.trading_graph:TradingAgentsGraph"

    # LLM related
    provider: Optional[str] = "openai"
    api_base: Optional[str] = "https://api.siliconflow.com/v1"
    api_key: Optional[str] = None
    model: Optional[str] = "deepseek-ai/DeepSeek-V3.2-Exp"
    temperature: float = 0.2
    top_p: float = 1.0
    max_tokens: Optional[int] = None
    timeout: Optional[int] = 120

    # Multi-agent workflow hooks
    system_prompt: Optional[str] = None
    roles_config: Optional[List[Dict[str, Any]]] = None
    tools_config: Optional[List[Dict[str, Any]]] = None
    routing: Optional[Dict[str, Any]] = None
    memory: Optional[Dict[str, Any]] = None
    judge: Optional[Dict[str, Any]] = None

    # JSON output constraints
    enforce_json: bool = True
    output_schema: Dict[str, Any] = field(default_factory=lambda: DEFAULT_OUTPUT_SCHEMA)

    # Misc passthrough
    extra: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_env(prefix: str = "CLQ_TA_") -> "TAConfig":
        """
        Hydrate configuration from environment variables.
        """

        def env(key: str, default: Optional[str] = None) -> Optional[str]:
            return os.environ.get(prefix + key, default)

        cfg = TAConfig(
            entrypoint=env(
                "ENTRYPOINT", "trading_agents.tradingagents.graph.trading_graph:TradingAgentsGraph"
            ),
            provider=env("PROVIDER", "deepseek"),
            api_base=env("API_BASE", "https://api.siliconflow.com/v1"),
            api_key=env("API_KEY"),
            model=env("MODEL", "deepseek-ai/DeepSeek-V3.2-Exp"),
            temperature=float(env("TEMPERATURE", "0.2")),
            top_p=float(env("TOP_P", "1.0")),
            max_tokens=int(env("MAX_TOKENS", "0")) or None,
            timeout=int(env("TIMEOUT", "120")),
            enforce_json=(env("ENFORCE_JSON", "true").lower() == "true"),
        )

        for key in ["OUTPUT_SCHEMA", "ROLES_CONFIG", "TOOLS_CONFIG", "ROUTING", "MEMORY", "JUDGE", "EXTRA"]:
            raw = env(key)
            if raw:
                try:
                    setattr(cfg, key.lower(), json.loads(raw))
                except Exception:
                    logger.warning("Environment variable %s is not valid JSON, ignoring.", prefix + key)

        return cfg

    @staticmethod
    def from_yaml(path: str) -> "TAConfig":
        if yaml is None:
            raise RuntimeError("pyyaml not installed; install pyyaml to load TAConfig from YAML.")
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if "trading_agents" in data:
            data = data["trading_agents"]
        if "output_schema" not in data:
            data["output_schema"] = DEFAULT_OUTPUT_SCHEMA
        return TAConfig(**data)

    # ---- helpers ---------------------------------------------------------

    def _default_tradingagents_config(self) -> Dict[str, Any]:
        """
        Loads TradingAgents' DEFAULT_CONFIG if available, else returns empty dict.
        """
        try:
            from external.trading_agents.tradingagents.default_config import DEFAULT_CONFIG as TA_DEFAULT_CONFIG

            return copy.deepcopy(TA_DEFAULT_CONFIG)
        except Exception:
            return {}

    def build_config(self) -> Dict[str, Any]:
        """
        Build the config dict expected by TradingAgentsGraph.
        """
        config = self._default_tradingagents_config()

        if isinstance(self.extra, dict):
            explicit_config = self.extra.get("config")
            if isinstance(explicit_config, dict):
                config.update(copy.deepcopy(explicit_config))
            override_config = self.extra.get("config_overrides")
            if isinstance(override_config, dict):
                config.update(copy.deepcopy(override_config))

        if self.provider:
            config["llm_provider"] = self.provider
        if self.api_base:
            config["backend_url"] = self.api_base
        if self.model:
            config["deep_think_llm"] = self.model
            config["quick_think_llm"] = self.model
        if self.max_tokens is not None:
            config["max_tokens"] = self.max_tokens
        if self.timeout is not None:
            config["timeout"] = self.timeout

        if isinstance(self.extra, dict):
            config_extra = self.extra.get("config_extra")
            if isinstance(config_extra, dict):
                config.update(copy.deepcopy(config_extra))

        if self.api_key:
            config["api_key"] = self.api_key

        return config

    def to_kwargs(self) -> Dict[str, Any]:
        """
        Convert into kwargs for the TradingAgents entrypoint.
        """
        kwargs: Dict[str, Any] = {}
        if isinstance(self.extra, dict):
            for key, value in self.extra.items():
                if key in {"config", "config_overrides", "config_extra"}:
                    continue
                kwargs[key] = value
        kwargs.setdefault("config", self.build_config())
        return kwargs


# === Orchestrator facade ==================================================


class TAOrchestrator:
    """
    Wrap a TradingAgents orchestrator and expose a simple ask(prompt) interface.
    """

    def __init__(self, config: TAConfig, llm_client: Optional[Any] = None, ta_entry: Optional[Any] = None):
        self.config = config
        self.llm_client = llm_client
        self._ta = ta_entry or self._build_ta_from_entrypoint()

    # ---- internal helpers ------------------------------------------------

    def _prepare_environment(self) -> None:
        """
        Seed environment variables needed by TradingAgents when using OpenAI-compatible endpoints.
        """
        provider = (self.config.provider or "").lower()
        if provider in {"openai", "openrouter", "ollama"}:
            if self.config.api_key:
                os.environ.setdefault("OPENAI_API_KEY", self.config.api_key)
            if self.config.api_base:
                os.environ.setdefault("OPENAI_BASE_URL", self.config.api_base)
        elif provider == "deepseek":
            if self.config.api_key:
                os.environ.setdefault("DEEPSEEK_API_KEY", self.config.api_key)
            if self.config.api_base:
                os.environ.setdefault("DEEPSEEK_API_BASE", self.config.api_base)
        if self.config.api_key:
            os.environ.setdefault("SILICONFLOW_API_KEY", self.config.api_key)
        if self.config.api_base:
            os.environ.setdefault("SILICONFLOW_API_BASE", self.config.api_base)
        if self.config.provider:
            os.environ.setdefault("TRADINGAGENTS_LLM_PROVIDER", self.config.provider)

    def _build_ta_from_entrypoint(self):
        entry = self.config.entrypoint
        try:
            # Fix for tradingagents internal absolute imports
            # TradingAgents modules use "from tradingagents.xxx import ..." 
            # but the module is actually at "trading_agents.tradingagents"
            # Add an alias to make it work
            if "trading_agents.tradingagents" in entry:
                try:
                    import trading_agents.tradingagents
                    if "tradingagents" not in sys.modules:
                        sys.modules["tradingagents"] = trading_agents.tradingagents
                        logger.info("Added module alias: tradingagents -> trading_agents.tradingagents")
                except Exception as alias_err:
                    logger.warning("Failed to create tradingagents module alias: %s", alias_err)
            
            factory = _load_obj(entry)
        except Exception as exc:
            logger.error("Failed to load TradingAgents entrypoint %s: %s", entry, exc)
            return None

        self._prepare_environment()

        kwargs = self.config.to_kwargs()
        if self.llm_client is not None:
            kwargs.setdefault("llm_client", self.llm_client)

        try:
            return factory(**kwargs)
        except TypeError as type_err:
            logger.warning("Factory call failed with kwargs %s, retrying with filtered kwargs: %s", kwargs, type_err)
            filtered_kwargs: Dict[str, Any] = {}
            try:
                signature = inspect.signature(factory)
                accepted = {
                    name
                    for name, param in signature.parameters.items()
                    if param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY)
                }
                filtered_kwargs = {k: v for k, v in kwargs.items() if k in accepted}
            except Exception:
                filtered_kwargs = {}

            if not filtered_kwargs and "config" in kwargs:
                filtered_kwargs = {"config": kwargs["config"]}
            elif "config" in kwargs and "config" not in filtered_kwargs:
                filtered_kwargs["config"] = kwargs["config"]

            try:
                return factory(**filtered_kwargs)
            except Exception as exc:
                logger.error("Failed to instantiate TradingAgents orchestrator after filtering: %s", exc)
                return None
        except Exception as exc:
            logger.error("Unexpected error instantiating TradingAgents orchestrator: %s", exc)
            return None

    # ---- public API ------------------------------------------------------

    def ask(self, prompt: str, **kwargs) -> Any:
        """
        Dispatch prompt to the underlying orchestrator, returning raw output.
        
        For TradingAgentsGraph, expects kwargs to contain:
        - symbol (str): Stock symbol/company name (e.g., 'AAPL')
        - trade_date (str): Trade date in format like '2024-01-01'
        
        Returns a dictionary with analysis results.
        """
        if self._ta is not None:
            call_kwargs = dict(kwargs)
            if self.config.enforce_json is not None:
                call_kwargs.setdefault("enforce_json", self.config.enforce_json)
            if self.config.output_schema is not None:
                call_kwargs.setdefault("output_schema", self.config.output_schema)

            # Check if this is TradingAgentsGraph and call propagate
            if hasattr(self._ta, "propagate") and callable(getattr(self._ta, "propagate")):
                return self._call_trading_agents_graph(prompt, call_kwargs)
            
            # Try standard run/ask methods
            if hasattr(self._ta, "run") and callable(getattr(self._ta, "run")):
                return _ensure_json_obj(self._ta.run(prompt=prompt, **call_kwargs))
            if hasattr(self._ta, "ask") and callable(getattr(self._ta, "ask")):
                return _ensure_json_obj(self._ta.ask(prompt=prompt, **call_kwargs))

            logger.warning("TradingAgents object has no run/ask/propagate method; returning its string representation.")
            return str(self._ta)

        raise RuntimeError(
            "TradingAgents orchestrator is not initialized. "
            "Ensure external/trading_agents is available and TAConfig.entrypoint points at a valid factory/class."
        )
    
    def _call_trading_agents_graph(self, prompt: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call TradingAgentsGraph.propagate and format the result as JSON.
        
        Args:
            prompt: Natural language prompt (can contain instructions)
            kwargs: Must contain 'symbol' and 'trade_date'
        
        Returns:
            Dictionary with trading analysis results
        """
        from datetime import datetime
        
        # Extract required parameters
        symbol = kwargs.get("symbol") or kwargs.get("company_name")
        trade_date = kwargs.get("trade_date") or kwargs.get("date")
        
        # If not provided in kwargs, try to use defaults
        if not symbol:
            # Try to extract from prompt (simple approach)
            import re
            # Look for stock symbols (2-5 uppercase letters)
            match = re.search(r'\b([A-Z]{2,5})\b', prompt)
            if match:
                symbol = match.group(1)
            else:
                symbol = "AAPL"  # Default symbol
                logger.warning("No symbol provided, using default: %s", symbol)
        
        if not trade_date:
            # Use today's date as default
            trade_date = datetime.now().strftime("%Y-%m-%d")
            logger.info("No trade_date provided, using today: %s", trade_date)
        
        try:
            # Call the propagate method
            logger.info("Calling TradingAgentsGraph.propagate(symbol=%s, trade_date=%s)", symbol, trade_date)
            final_state, processed_signal = self._ta.propagate(symbol, trade_date)
            
            # Format the result as JSON
            result = {
                "symbol": symbol,
                "trade_date": trade_date,
                "decision": processed_signal.strip() if isinstance(processed_signal, str) else str(processed_signal),
                "analysis": {
                    "market_report": final_state.get("market_report", ""),
                    "sentiment_report": final_state.get("sentiment_report", ""),
                    "news_report": final_state.get("news_report", ""),
                    "fundamentals_report": final_state.get("fundamentals_report", ""),
                },
                "investment_plan": final_state.get("investment_plan", ""),
                "final_trade_decision": final_state.get("final_trade_decision", ""),
                "trader_plan": final_state.get("trader_investment_plan", ""),
            }
            
            # Add debate information if available
            if "investment_debate_state" in final_state:
                debate = final_state["investment_debate_state"]
                result["debate"] = {
                    "bull_conclusion": debate.get("bull_history", [""])[-1] if debate.get("bull_history") else "",
                    "bear_conclusion": debate.get("bear_history", [""])[-1] if debate.get("bear_history") else "",
                    "judge_decision": debate.get("judge_decision", ""),
                }
            
            return result
            
        except Exception as exc:
            logger.error("Error calling TradingAgentsGraph.propagate: %s", exc, exc_info=True)
            # Return error in JSON format
            return {
                "error": str(exc),
                "symbol": symbol,
                "trade_date": trade_date,
                "decision": "ERROR",
            }

    # ---- construction shortcuts -----------------------------------------

    @classmethod
    def from_yaml(cls, path: str, llm_client: Optional[Any] = None) -> "TAOrchestrator":
        cfg = TAConfig.from_yaml(path)
        return cls(config=cfg, llm_client=llm_client)

    @classmethod
    def from_env(cls, prefix: str = "CLQ_TA_", llm_client: Optional[Any] = None) -> "TAOrchestrator":
        cfg = TAConfig.from_env(prefix=prefix)
        return cls(config=cfg, llm_client=llm_client)


# End of file
