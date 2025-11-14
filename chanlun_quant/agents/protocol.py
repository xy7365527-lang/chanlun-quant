from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class ResearchRequest:
    """
    标准化的 Trading Agents 请求结构。

    当外部研究服务接入时，适配器应接受此结构或其字典形式，返回 ResearchPacket 兼容的数据。
    """

    symbol: str
    stage: str
    prompt: str
    schema: Dict[str, Any]
    structure_summary: Dict[str, Any] = field(default_factory=dict)
    position_summary: Dict[str, Any] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=lambda: datetime.utcnow())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "stage": self.stage,
            "prompt": self.prompt,
            "schema": self.schema,
            "structure_summary": dict(self.structure_summary),
            "position_summary": dict(self.position_summary),
            "generated_at": self.generated_at.isoformat() + "Z",
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ResearchRequest":
        generated_raw = payload.get("generated_at")
        if isinstance(generated_raw, str):
            try:
                generated_at = datetime.fromisoformat(generated_raw.replace("Z", "+00:00"))
            except ValueError:
                generated_at = datetime.utcnow()
        else:
            generated_at = datetime.utcnow()

        return cls(
            symbol=str(payload.get("symbol", "")),
            stage=str(payload.get("stage", "")),
            prompt=str(payload.get("prompt", "")),
            schema=dict(payload.get("schema", {}) or {}),
            structure_summary=dict(payload.get("structure_summary", {}) or {}),
            position_summary=dict(payload.get("position_summary", {}) or {}),
            generated_at=generated_at,
            metadata=dict(payload.get("metadata", {}) or {}),
        )


__all__ = ["ResearchRequest"]

