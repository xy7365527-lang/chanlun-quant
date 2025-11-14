from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from chanlun_quant.agents.protocol import ResearchRequest
from chanlun_quant.plugins.loader import instantiate

LOGGER = logging.getLogger(__name__)


@dataclass
class ResearchItem:
    symbol: str
    score: float = 0.0
    recommendation: str = "watch"
    reason: str = ""
    ta_gate: bool = True
    risk_mult: float = 1.0
    L_mult: float = 1.0
    sentiment: str = "neutral"
    fundamentals: str = ""
    risk_flags: List[str] = field(default_factory=list)
    risk_notes: List[str] = field(default_factory=list)
    time_horizon: str = "swing"
    thesis: Dict[str, Any] = field(default_factory=dict)
    valid_until: Optional[datetime] = None
    kill_switch: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any], *, symbol_fallback: str) -> "ResearchItem":
        symbol = data.get("symbol") or symbol_fallback
        valid_until_raw = data.get("valid_until")
        if isinstance(valid_until_raw, str) and valid_until_raw:
            try:
                valid_until = datetime.fromisoformat(valid_until_raw.replace("Z", "+00:00")).astimezone()
            except ValueError:
                valid_until = None
        elif isinstance(valid_until_raw, datetime):
            valid_until = valid_until_raw
        else:
            valid_until = None

        score_value = data.get("score", data.get("ta_score", 0.0))
        recommendation_value = data.get("recommendation", data.get("ta_recommendation", "watch"))
        gate_value = data.get("ta_gate", data.get("gate", True))

        return cls(
            symbol=symbol,
            score=float(score_value or 0.0),
            recommendation=str(recommendation_value or "watch"),
            reason=str(data.get("reason", "")),
            ta_gate=bool(gate_value),
            risk_mult=float(data.get("risk_mult", 1.0) or 1.0),
            L_mult=float(data.get("L_mult", 1.0) or 1.0),
            sentiment=str(data.get("sentiment", "neutral") or "neutral"),
            fundamentals=str(data.get("fundamentals", "")),
            risk_flags=list(data.get("risk_flags", []) or []),
            risk_notes=list(data.get("risk_notes", []) or []),
            time_horizon=str(data.get("time_horizon", "swing") or "swing"),
            thesis=dict(data.get("thesis", {}) or {}),
            valid_until=valid_until,
            kill_switch=bool(data.get("kill_switch", False)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "score": self.score,
            "ta_score": self.score,
            "recommendation": self.recommendation,
            "ta_recommendation": self.recommendation,
            "reason": self.reason,
            "ta_gate": self.ta_gate,
            "risk_mult": self.risk_mult,
            "L_mult": self.L_mult,
            "sentiment": self.sentiment,
            "fundamentals": self.fundamentals,
            "risk_flags": list(self.risk_flags),
            "risk_notes": list(self.risk_notes),
            "time_horizon": self.time_horizon,
            "thesis": dict(self.thesis),
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "kill_switch": self.kill_switch,
        }

    def is_valid(self, now: datetime) -> bool:
        if self.valid_until and now.tzinfo and self.valid_until.tzinfo:
            return now <= self.valid_until
        if self.valid_until and not now.tzinfo:
            return now <= self.valid_until.replace(tzinfo=None)
        return True


@dataclass
class ResearchPacket:
    analysis: List[ResearchItem] = field(default_factory=list)
    top_picks: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.utcnow())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get(self, symbol: str) -> Optional[ResearchItem]:
        symbol_upper = symbol.upper()
        for item in self.analysis:
            if item.symbol.upper() == symbol_upper:
                return item
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analysis": [item.to_dict() for item in self.analysis],
            "top_picks": list(self.top_picks),
            "generated_at": self.generated_at.replace(microsecond=0).isoformat() + "Z",
            "metadata": dict(self.metadata),
        }


class TradingAgentsManager:
    def __init__(self, cfg, *, now_fn=datetime.utcnow) -> None:
        self.enabled: bool = bool(getattr(cfg, "ta_enabled", False))
        self.score_threshold: float = float(getattr(cfg, "ta_score_threshold", 0.6) or 0.0)
        self.gate_mode: str = str(getattr(cfg, "ta_gate_mode", "soft") or "soft").lower()
        self.cache_minutes: float = float(getattr(cfg, "ta_cache_minutes", 30.0) or 0.0)
        self.adapter_class: str = str(getattr(cfg, "ta_adapter_class", "") or "")
        self.adapter_kwargs_json: str = str(getattr(cfg, "ta_kwargs_json", "") or "")
        self.skip_on_fail: bool = bool(getattr(cfg, "ta_skip_on_fail", True))
        self._now = now_fn
        self._cache: Dict[str, Tuple[datetime, ResearchPacket]] = {}
        self._cache_ttl = timedelta(minutes=max(1.0, self.cache_minutes))
        self._adapter = None

        self._stage_refresh_factor = {
            "INITIAL": 1.0,
            "COST_DOWN": 3.0,
            "ZERO_COST": 6.0,
            "NEG_COST": 6.0,
        }

        if self.enabled and self.adapter_class:
            try:
                kwargs = json.loads(self.adapter_kwargs_json) if self.adapter_kwargs_json else {}
                self._adapter = instantiate(self.adapter_class, **kwargs)
            except Exception as exc:  # pragma: no cover - defensive import failure
                LOGGER.warning("Failed to instantiate TradingAgents adapter %s: %s", self.adapter_class, exc)
                self._adapter = None

    def get_research(
        self,
        symbol: str,
        structure_packet: Dict[str, Any],
        stage: str,
    ) -> Tuple[Optional[ResearchPacket], Optional[ResearchItem]]:
        if not self.enabled:
            return None, None

        now = self._now()
        cached = self._cache.get(symbol)

        stage_norm = (stage or "").upper()

        packet: Optional[ResearchPacket] = None
        cached_item: Optional[ResearchItem] = None

        if cached:
            packet = cached[1]
            cached_item = packet.get(symbol)

        needs_refresh = False
        if stage_norm == "WITHDRAW" and cached_item:
            item_valid = cached_item.is_valid(now)
            if item_valid:
                return packet, cached_item
        elif stage_norm == "WITHDRAW" and not cached and self.skip_on_fail:
            LOGGER.debug("TA skip for symbol=%s stage=WITHDRAW (no refresh required)", symbol)
            return None, None

        if not cached_item:
            needs_refresh = True
        else:
            if not cached_item.is_valid(now):
                needs_refresh = True
            elif self._should_refresh(stage_norm, cached[0], now):
                needs_refresh = True

        if not needs_refresh and packet:
            return packet, cached_item

        if stage_norm == "WITHDRAW" and self.skip_on_fail:
            return packet, cached_item

        packet = self._fetch(symbol, structure_packet, stage_norm)
        if packet is None:
            if cached:
                return cached[1], cached_item
            return None, None

        self._cache[symbol] = (now, packet)
        return packet, packet.get(symbol)

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _should_refresh(self, stage: str, cached_at: datetime, now: datetime) -> bool:
        age = now - cached_at
        factor = self._stage_refresh_factor.get(stage, 4.0)
        interval = self._cache_ttl * factor
        return age > interval

    def _fetch(self, symbol: str, structure_packet: Dict[str, Any], stage: str) -> Optional[ResearchPacket]:
        prompt_payload = self._build_prompt_packet(symbol, structure_packet, stage)

        response: Optional[Any] = None
        if self._adapter is not None:
            try:
                if hasattr(self._adapter, "generate"):
                    response = self._adapter.generate(prompt_payload)
                elif hasattr(self._adapter, "ask_json"):
                    response = self._adapter.ask_json(prompt_payload)
                elif callable(self._adapter):
                    response = self._adapter(prompt_payload)
            except Exception as exc:  # pragma: no cover - defensive call
                LOGGER.warning("TradingAgents adapter call failed: %s", exc)
                response = None

        if response is None:
            response = self._default_packet(symbol)
        packet = self._parse_packet(response, symbol)
        return packet

    @staticmethod
    def _default_packet(symbol: str) -> Dict[str, Any]:
        return {
            "analysis": [
                {
                    "symbol": symbol,
                    "ta_score": 0.5,
                    "ta_recommendation": "watch",
                    "reason": "default stub",
                    "ta_gate": True,
                    "risk_mult": 1.0,
                    "L_mult": 1.0,
                    "sentiment": "neutral",
                    "fundamentals": "n/a",
                    "risk_flags": [],
                    "risk_notes": [],
                    "time_horizon": "swing",
                    "thesis": {
                        "technical": "结构信息不足",
                        "fundamental": "无可用基本面数据",
                        "macro": "无重大宏观事件",
                    },
                    "valid_until": datetime.utcnow().isoformat() + "Z",
                    "kill_switch": False,
                }
            ],
            "top_picks": [symbol],
            "metadata": {"generated_by": "default_stub"},
        }

    def _parse_packet(self, data: Any, symbol: str) -> Optional[ResearchPacket]:
        if isinstance(data, ResearchPacket):
            return data
        if not isinstance(data, dict):
            return None

        analysis_raw = data.get("analysis") or []
        analysis: List[ResearchItem] = []
        for item_raw in analysis_raw:
            if isinstance(item_raw, dict):
                analysis.append(ResearchItem.from_dict(item_raw, symbol_fallback=symbol))
        if not analysis:
            analysis.append(ResearchItem(symbol=symbol))

        top_picks = data.get("top_picks") or [analysis[0].symbol]
        generated_raw = data.get("generated_at")
        generated_at = self._parse_datetime(generated_raw)

        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}

        return ResearchPacket(analysis=analysis, top_picks=list(top_picks), generated_at=generated_at, metadata=metadata)

    def _build_prompt_packet(self, symbol: str, structure_packet: Dict[str, Any], stage: str) -> Dict[str, Any]:
        payload = dict(structure_packet)
        payload.setdefault("symbol", symbol)
        try:
            prompt = build_ta_prompt(payload)
        except Exception:  # pragma: no cover - fallback if template formatting fails
            prompt = json.dumps(payload, ensure_ascii=False)
        request = ResearchRequest(
            symbol=symbol,
            stage=stage,
            prompt=prompt,
            schema=json.loads(get_ta_schema()),
            structure_summary=dict(structure_packet.get("structure_summary", structure_packet)),
            position_summary=dict(structure_packet.get("position_summary", {})),
        )
        return request.to_dict()


def build_ta_prompt(context: Dict[str, Any]) -> str:
    from .templates import TA_RESEARCH_OUTPUT_SCHEMA, TA_RESEARCH_PROMPT

    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    return TA_RESEARCH_PROMPT.format(context=context_json, schema=TA_RESEARCH_OUTPUT_SCHEMA)


def get_ta_schema() -> str:
    from .templates import TA_RESEARCH_OUTPUT_SCHEMA

    return TA_RESEARCH_OUTPUT_SCHEMA
