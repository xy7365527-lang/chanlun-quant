from __future__ import annotations

import os
from dataclasses import dataclass, replace


@dataclass
class Config:
    """
    Global configuration. Use Config.from_env() to override defaults with CLQ_* environment variables.
    """

    # Pen/segment/feature sequence/central/divergence parameters
    min_bars_per_pen: int = 5
    gap_tolerance: float = 0.0
    strict_feature_sequence: bool = True
    central_overlap_ratio: float = 0.2
    max_central_segments: int = 9
    leave_central_threshold: float = 0.15
    divergence_threshold: float = 0.8

    # MACD area mode
    macd_area_mode: str = "hist"

    # Multi-level defaults
    levels: tuple[str, ...] = ("5m", "30m", "1d")

    # LLM configuration
    use_llm: bool = True
    llm_model: str = "gpt-4"
    llm_temperature: float = 0.0
    llm_provider: str = "mock"
    llm_api_base: str = ""
    llm_api_key: str = ""
    external_broker_class: str = ""
    external_llm_client_class: str = ""
    external_datafeed_class: str = ""
    external_kwargs_json: str = ""

    # Broker/runtime configuration
    live_trading: bool = False
    ib_host: str = "127.0.0.1"
    ib_port: int = 4002
    ib_client_id: int = 1
    symbol: str = "SPY"

    # Risk/action-space constraints
    max_leverage: float = 1.0
    max_position: int = 10_000
    max_notional: float = 1_000_000.0
    cooldown_bars: int = 3
    min_qty: int = 1
    step_qty: int = 1

    @classmethod
    def from_env(cls, **overrides) -> "Config":
        """Read CLQ_* environment variables and build a config instance."""
        env = os.environ.get

        def as_int(name: str, default: int) -> int:
            value = env(name)
            return default if value is None else int(value)

        def as_float(name: str, default: float) -> float:
            value = env(name)
            return default if value is None else float(value)

        def as_bool(name: str, default: bool) -> bool:
            value = env(name)
            if value is None:
                return default
            value = value.strip().lower()
            return value in {"1", "true", "yes", "on"}

        def as_str(name: str, default: str) -> str:
            value = env(name)
            return default if value is None else value

        def as_levels(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
            value = env(name)
            if value is None:
                return default
            parts = [part.strip() for part in value.split(",") if part.strip()]
            return tuple(parts) if parts else default

        instance = cls(
            min_bars_per_pen=as_int("CLQ_MIN_BARS_PER_PEN", cls.min_bars_per_pen),
            gap_tolerance=as_float("CLQ_GAP_TOLERANCE", cls.gap_tolerance),
            strict_feature_sequence=as_bool("CLQ_STRICT_FEATURE_SEQUENCE", cls.strict_feature_sequence),
            central_overlap_ratio=as_float("CLQ_CENTRAL_OVERLAP_RATIO", cls.central_overlap_ratio),
            max_central_segments=as_int("CLQ_MAX_CENTRAL_SEGMENTS", cls.max_central_segments),
            leave_central_threshold=as_float("CLQ_LEAVE_CENTRAL_THRESHOLD", cls.leave_central_threshold),
            divergence_threshold=as_float("CLQ_DIVERGENCE_THRESHOLD", cls.divergence_threshold),
            macd_area_mode=as_str("CLQ_MACD_AREA_MODE", cls.macd_area_mode),
            levels=as_levels("CLQ_LEVELS", cls.levels),
            use_llm=as_bool("CLQ_USE_LLM", cls.use_llm),
            llm_provider=as_str("CLQ_LLM_PROVIDER", cls.llm_provider),
            llm_api_base=as_str("CLQ_LLM_API_BASE", cls.llm_api_base),
            llm_api_key=as_str("CLQ_LLM_API_KEY", cls.llm_api_key),
            llm_model=as_str("CLQ_LLM_MODEL", cls.llm_model),
            llm_temperature=as_float("CLQ_LLM_TEMPERATURE", cls.llm_temperature),
            external_broker_class=as_str("CLQ_BROKER_CLASS", cls.external_broker_class),
            external_llm_client_class=as_str("CLQ_LLM_CLIENT_CLASS", cls.external_llm_client_class),
            external_datafeed_class=as_str("CLQ_DATAFEED_CLASS", cls.external_datafeed_class),
            external_kwargs_json=as_str("CLQ_EXT_KWARGS", cls.external_kwargs_json),
            live_trading=as_bool("CLQ_LIVE_TRADING", cls.live_trading),
            ib_host=as_str("CLQ_IB_HOST", cls.ib_host),
            ib_port=as_int("CLQ_IB_PORT", cls.ib_port),
            ib_client_id=as_int("CLQ_IB_CLIENT_ID", cls.ib_client_id),
            symbol=as_str("CLQ_SYMBOL", cls.symbol),
            max_leverage=as_float("CLQ_MAX_LEVERAGE", cls.max_leverage),
            max_position=as_int("CLQ_MAX_POSITION", cls.max_position),
            max_notional=as_float("CLQ_MAX_NOTIONAL", cls.max_notional),
            cooldown_bars=as_int("CLQ_COOLDOWN_BARS", cls.cooldown_bars),
            min_qty=as_int("CLQ_MIN_QTY", cls.min_qty),
            step_qty=as_int("CLQ_STEP_QTY", cls.step_qty),
        )

        if overrides:
            instance = replace(instance, **overrides)
        return instance
