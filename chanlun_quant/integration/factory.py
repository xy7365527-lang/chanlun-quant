from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..ai.interface import ChanLLM, ExternalLLMClientAdapter, LLMClient
from ..broker import IBBroker
from ..broker.interface import BrokerInterface, ExternalBrokerAdapter, SimulatedBroker
from ..config import Config
from ..datafeed.interface import DataFeed, ExternalDataFeedAdapter
from ..integration.inspector import inspect_external
from ..plugins.loader import instantiate


def _maybe_kwargs(cfg: Config) -> Dict[str, Any]:
    raw = (cfg.external_kwargs_json or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _build_llm(cfg: Config, kwargs: Dict[str, Any], report: Dict[str, Dict[str, Any]]) -> Optional[ChanLLM]:
    if not cfg.use_llm:
        return None
    if cfg.external_llm_client_class and report.get("llm", {}).get("loaded"):
        ext_client = instantiate(cfg.external_llm_client_class, **kwargs)
        client = ExternalLLMClientAdapter(ext_client)
        return ChanLLM(client=client)
    return ChanLLM(client=LLMClient())


def _build_broker(cfg: Config, kwargs: Dict[str, Any], report: Dict[str, Dict[str, Any]]) -> BrokerInterface:
    if cfg.external_broker_class and report.get("broker", {}).get("loaded"):
        ext_broker = instantiate(cfg.external_broker_class, **kwargs)
        return ExternalBrokerAdapter(ext_broker)
    if cfg.live_trading:
        return IBBroker(
            host=cfg.ib_host,
            port=cfg.ib_port,
            client_id=cfg.ib_client_id,
            exchange=kwargs.get("ib_exchange", "SMART"),
            currency=kwargs.get("ib_currency", "USD"),
        )
    return SimulatedBroker()


def _build_datafeed(cfg: Config, kwargs: Dict[str, Any], report: Dict[str, Dict[str, Any]]) -> Optional[DataFeed]:
    if not (cfg.external_datafeed_class and report.get("datafeed", {}).get("loaded")):
        return None
    ext_feed = instantiate(cfg.external_datafeed_class, **kwargs)
    return ExternalDataFeedAdapter(ext_feed)


@dataclass
class ExternalBundle:
    broker: BrokerInterface
    datafeed: Optional[DataFeed]
    llm: Optional[ChanLLM]
    report: Dict[str, Dict[str, Any]]


def load_external_components(cfg: Config) -> ExternalBundle:
    """Load external integrations according to config, returning adapters + inspection report."""

    kwargs = _maybe_kwargs(cfg)
    report = inspect_external(cfg)

    broker = _build_broker(cfg, kwargs, report)
    datafeed = _build_datafeed(cfg, kwargs, report)
    llm = _build_llm(cfg, kwargs, report)

    return ExternalBundle(broker=broker, datafeed=datafeed, llm=llm, report=report)


__all__ = ["ExternalBundle", "load_external_components"]
