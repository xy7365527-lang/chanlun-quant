from __future__ import annotations

import json
from typing import Any, Dict, Optional

from chanlun_quant.ai import templates
from chanlun_quant.ai.payload import build_ai_context, to_ib_order, validate_ai_instruction

try:  # optional dependency for live providers
    import requests  # type: ignore
except Exception:  # pragma: no cover - ensure offline fallback
    requests = None


class LLMClient:
    """
    Lightweight multi-provider client.

    provider:
      - "mock": deterministic local responses
      - "deepseek": POST {api_base}/chat/completions
      - "openai":  POST {api_base}/v1/chat/completions (gpt-5-thinking)
    """

    def __init__(
        self,
        provider: str = "mock",
        api_base: str = "",
        api_key: str = "",
        model: str = "",
    ) -> None:
        self.provider = (provider or "mock").lower()
        self.api_base = api_base.rstrip("/") if api_base else ""
        self.api_key = api_key or ""
        self.model = model or ""

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def ask_json(self, prompt: str) -> Dict[str, Any]:
        if self._should_mock():
            return self._mock_json(prompt)

        try:
            response = self._post_chat(prompt)
            content = self._extract_content(response)
            if not content:
                return {"ok": False, "error": "empty content", "raw": response}
            return self._extract_json(content)
        except Exception as exc:  # pragma: no cover - network fallback
            result = self._mock_json(prompt)
            result["_fallback"] = str(exc)
            return result

    def ask_text(self, prompt: str) -> str:
        if self._should_mock():
            return "mock"
        try:
            response = self._post_chat(prompt)
            content = self._extract_content(response)
            return content or "mock"
        except Exception:  # pragma: no cover - network fallback
            return "mock"

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _should_mock(self) -> bool:
        return (
            self.provider == "mock"
            or requests is None
            or not self.api_base
            or not self.api_key
            or not self.model
        )

    def _mock_json(self, prompt: str) -> Dict[str, Any]:
        upper = prompt.upper()
        if "FUGUE" in upper or '"FUGUE_STATE"' in upper:
            return {
                "fugue_state": "共振",
                "score": 0.7,
                "confidence": 0.7,
                "action": "顺势做多",
                "reason": "mock",
            }
        if "MOMENTUM" in upper or '"MOMENTUM"' in upper:
            return {"momentum": "增强", "confidence": 0.65, "reason": "mock"}
        if "VERIFY" in upper and "SEGMENT" in upper or '"SEGMENT_END"' in upper:
            return {"segment_end": False, "confidence": 0.6, "reason": "mock"}
        if "DECIDE_ACTION" in upper or "EXECUTION PLANNER" in upper:
            return {"action": "HOLD", "quantity": 0, "leverage": 0, "reason": "mock"}
        return {"ok": True, "reason": "mock"}

    def _post_chat(self, prompt: str) -> Dict[str, Any]:
        assert requests is not None  # guarded by _should_mock
        endpoint = (
            "/v1/chat/completions" if self.provider == "openai" else "/chat/completions"
        )
        url = f"{self.api_base}{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()

    def _extract_content(self, data: Dict[str, Any]) -> str:
        if not isinstance(data, dict):
            return ""
        choices = data.get("choices") or data.get("data") or []
        if choices and isinstance(choices, list):
            message = choices[0].get("message") or choices[0].get("delta") or {}
            if isinstance(message, dict):
                return message.get("content") or ""
        return data.get("content", "")

    def _extract_json(self, text: str) -> Dict[str, Any]:
        try:
            return json.loads(text)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if 0 <= start < end:
                try:
                    return json.loads(text[start : end + 1])
                except Exception:
                    pass
            return {"ok": False, "raw": text}


class ChanLLM:
    """High-level LLM wrapper with provider fallback support."""

    def __init__(
        self,
        client: Optional[LLMClient] = None,
        cfg: Optional[object] = None,
    ) -> None:
        if client is not None:
            self.client = client
        else:
            if cfg is not None and getattr(cfg, "use_llm", True):
                self.client = LLMClient(
                    provider=getattr(cfg, "llm_provider", "mock"),
                    api_base=getattr(cfg, "llm_api_base", ""),
                    api_key=getattr(cfg, "llm_api_key", ""),
                    model=getattr(cfg, "llm_model", ""),
                )
            else:
                self.client = LLMClient(provider="mock")

    def verify_segment_end(self, context: Dict[str, Any]) -> Dict[str, Any]:
        prompt = templates.VERIFY_SEGMENT_END_JSON.format(context=_format_context(context))
        return self.client.ask_json(prompt)

    def explain_signal(self, context: Dict[str, Any]) -> str:
        prompt = templates.EXPLAIN_SIGNAL_CN_TEXT.format(context=_format_context(context))
        return self.client.ask_text(prompt)

    def assess_fugue(self, context: Dict[str, Any]) -> Dict[str, Any]:
        prompt = templates.MULTI_LEVEL_FUGUE_JSON.format(context=_format_context(context))
        return self.client.ask_json(prompt)

    def interpret_momentum(self, context: Dict[str, Any]) -> Dict[str, Any]:
        prompt = templates.MOMENTUM_INTERPRET_JSON.format(context=_format_context(context))
        return self.client.ask_json(prompt)

    def decide_action(self, structure_state, position_state, cfg) -> Dict[str, Any]:
        ctx = build_ai_context(structure_state, position_state, cfg)
        prompt = templates.DECIDE_ACTION_JSON.format(context=_format_context(ctx))
        instruction = self.client.ask_json(prompt)

        valid, errors = validate_ai_instruction(instruction, position_state, cfg)
        ib_order = None
        if valid and instruction.get("action") in {"BUY", "SELL"} and instruction.get("quantity", 0) > 0:
            ib_order = to_ib_order(instruction, cfg)
        if not valid:
            instruction = {
                "action": "HOLD",
                "quantity": 0,
                "leverage": 0,
                "reason": "invalid: " + ";".join(errors),
            }

        return {"instruction": instruction, "valid": valid, "errors": errors, "ib_order": ib_order}


def _format_context(context: Any) -> str:
    if isinstance(context, str):
        return context
    try:
        return json.dumps(context, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        return repr(context)
