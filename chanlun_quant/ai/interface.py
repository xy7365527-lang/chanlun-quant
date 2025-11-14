from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from chanlun_quant.ai.payload import ACTION_SCHEMA, build_ai_context, validate_ai_instruction
from chanlun_quant.ai.templates import (
    DECIDE_ACTION_JSON,
    MOMENTUM_INTERPRET_JSON,
    MULTI_LEVEL_FUGUE_JSON,
    POST_DIVERGENCE_JSON,
    VERIFY_SEGMENT_END_JSON,
)
from chanlun_quant.types import PositionState, StructureState


class LLMError(RuntimeError):
    """Raised when an LLM interaction fails."""


class LLMClient:
    """Minimal client abstraction wrapping either mock or real providers."""

    def __init__(
        self,
        provider: str = "mock",
        model: str = "gpt-4",
        temperature: float = 0.0,
        *,
        backend: Optional[Any] = None,
        mock_response: Optional[Dict[str, Any]] = None,
        api_base: str = "",
        api_key: str = "",
    ) -> None:
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.api_base = api_base
        self.api_key = api_key
        self._backend = backend
        self._mock_response = mock_response or {"action": "HOLD", "quantity": 0.0, "reason": "mock"}
        self._effective_provider = provider if (provider == "mock" or backend is not None) else "mock"

    def ask_json(self, prompt: str, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self._effective_provider == "mock":
            return dict(self._mock_response)

        if not self._backend:
            raise LLMError("No backend configured")

        try:
            response = self._backend.ask_json(
                prompt,
                model=self.model,
                temperature=self.temperature,
                schema=schema,
            )
        except Exception as exc:  # pragma: no cover - defensive
            raise LLMError(f"LLM backend error: {exc}") from exc

        if not isinstance(response, dict):
            raise LLMError("LLM response must be dict")
        return response

    def ask_text(self, prompt: str) -> str:
        if self._effective_provider == "mock":
            if isinstance(self._mock_response, dict):
                return str(self._mock_response.get("reason", "mock"))
            return str(self._mock_response)

        if not self._backend:
            raise LLMError("No backend configured")

        if hasattr(self._backend, "ask_text"):
            try:
                response = self._backend.ask_text(prompt, model=self.model, temperature=self.temperature)
            except Exception as exc:  # pragma: no cover - defensive
                raise LLMError(f"LLM backend error: {exc}") from exc
            return response if isinstance(response, str) else str(response)

        json_payload = self.ask_json(prompt)
        return json.dumps(json_payload, ensure_ascii=False)


class ExternalLLMClientAdapter(LLMClient):
    """Adapter to reuse arbitrary chat clients via the ``LLMClient`` API."""

    def __init__(self, ext_client: Any) -> None:
        super().__init__(provider="mock")
        self.provider = "external"
        self.ext = ext_client

    def ask_json(self, prompt: str, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if hasattr(self.ext, "ask_json"):
            method = getattr(self.ext, "ask_json")
            try:
                if schema is not None:
                    result = method(prompt, schema=schema)
                else:
                    result = method(prompt)
            except TypeError:
                result = method(prompt)
        elif hasattr(self.ext, "chat"):
            method = getattr(self.ext, "chat")
            result = method(prompt)
        else:
            raise LLMError("external client does not expose ask_json/chat")

        payload = self._coerce_to_dict(result)
        if not isinstance(payload, dict):
            raise LLMError("external client returned non-dict payload")
        return payload

    def ask_text(self, prompt: str) -> str:
        if hasattr(self.ext, "ask_text"):
            return self.ext.ask_text(prompt)
        if hasattr(self.ext, "chat"):
            result = self.ext.chat(prompt)
            text = self._extract_text(result)
            if text is not None:
                return text
        try:
            json_payload = self.ask_json(prompt)
        except LLMError:
            return ""
        return json.dumps(json_payload, ensure_ascii=False)

    def _coerce_to_dict(self, payload: Any) -> Dict[str, Any] | Any:
        if isinstance(payload, dict):
            return payload
        if hasattr(payload, "model_dump"):
            try:
                return payload.model_dump()
            except Exception:
                pass
        if hasattr(payload, "to_dict"):
            try:
                return payload.to_dict()
            except Exception:
                pass
        content = getattr(payload, "content", None)
        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"content": content}
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return {"content": payload}
        return payload

    def _extract_text(self, payload: Any) -> Optional[str]:
        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            if "content" in payload:
                return str(payload["content"])
            return json.dumps(payload, ensure_ascii=False)
        content = getattr(payload, "content", None)
        if content is not None:
            if isinstance(content, str):
                return content
            if isinstance(content, dict):
                return json.dumps(content, ensure_ascii=False)
        return None


class StructureLLM:
    """JSON-only helper for structure related queries."""

    def __init__(self, client: Optional[LLMClient] = None) -> None:
        self.client = client

    def _ensure_client(self) -> LLMClient:
        if self.client is None:
            raise RuntimeError("StructureLLM client not configured")
        return self.client

    def _ask_json(
        self,
        template: str,
        context: Dict[str, Any],
        *,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        client = self._ensure_client()
        context_json = json.dumps(context, ensure_ascii=False, indent=2)
        if "{context}" in template:
            prompt_core = template.replace("{context}", context_json)
        else:
            prompt_core = template
        if "Input:\n" not in prompt_core:
            prompt = f"{prompt_core}\n\nInput:\n{context_json}\n"
        else:
            prompt = prompt_core
        return client.ask_json(prompt, schema=schema)

    def verify_segment_end(self, context: Dict[str, Any], *, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._ask_json(VERIFY_SEGMENT_END_JSON, context, schema=schema)

    def summarize_fugue(self, context: Dict[str, Any], *, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._ask_json(MULTI_LEVEL_FUGUE_JSON, context, schema=schema)

    def interpret_momentum(self, context: Dict[str, Any], *, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._ask_json(MOMENTUM_INTERPRET_JSON, context, schema=schema)

    def analyze_post_divergence(self, context: Dict[str, Any], *, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._ask_json(POST_DIVERGENCE_JSON, context, schema=schema)


@dataclass
class DecisionResult:
    action: str
    quantity: float
    confidence: float
    reason: str
    raw: Dict[str, Any]
    price_hint: Optional[float] = None
    reasons: Optional[List[str]] = None
    cost_covered_after: Optional[bool] = None


@dataclass
class PlanDecisionResult:
    decisions: List[Dict[str, Any]]
    notes: str
    raw: Dict[str, Any]


@dataclass
class StageMemoryResult:
    stage_after: Optional[str]
    cb_snapshot: Optional[Dict[str, Any]]
    next_milestone: Optional[Dict[str, Any]]
    raw: Dict[str, Any]


class ChanLLM:
    """High level trading advisor built on top of :class:`StructureLLM`."""

    def __init__(
        self,
        client: Optional[LLMClient] = None,
        *,
        structure_llm: Optional[StructureLLM] = None,
        cfg: Optional[Any] = None,
        max_retries: int = 0,
        retry_delay: float = 0.5,
    ) -> None:
        if client is None and cfg is not None:
            client = LLMClient(
                provider=getattr(cfg, "llm_provider", "mock"),
                model=getattr(cfg, "llm_model", "gpt-4"),
                temperature=getattr(cfg, "llm_temperature", 0.0),
                api_base=getattr(cfg, "llm_api_base", ""),
                api_key=getattr(cfg, "llm_api_key", ""),
            )

        if structure_llm is not None and structure_llm.client is not None and client is None:
            client = structure_llm.client

        if client is None:
            client = LLMClient()

        if structure_llm is None:
            structure_llm = StructureLLM(client)
        elif structure_llm.client is None:
            structure_llm.client = client

        self.client = client
        self.structure_llm = structure_llm
        self.max_retries = max(0, int(max_retries))
        self.retry_delay = max(0.0, float(retry_delay))

    def _decide_from_context(self, context: Dict[str, Any], *, schema: Optional[Dict[str, Any]] = None) -> DecisionResult:
        attempt = 0
        last_error: Optional[Exception] = None
        while attempt <= self.max_retries:
            try:
                result = self.structure_llm._ask_json(DECIDE_ACTION_JSON, context, schema=schema)
                action = str(result.get("action", "HOLD"))
                try:
                    quantity = float(result.get("quantity", 0.0))
                except (TypeError, ValueError):
                    quantity = 0.0
                try:
                    confidence = float(result.get("confidence", 0.0))
                except (TypeError, ValueError):
                    confidence = 0.0
                price_hint_raw = result.get("price_hint")
                try:
                    price_hint = float(price_hint_raw) if price_hint_raw is not None else None
                except (TypeError, ValueError):
                    price_hint = None
                reasons_raw = result.get("reasons")
                reasons: Optional[List[str]]
                if isinstance(reasons_raw, list):
                    reasons = [str(item) for item in reasons_raw if str(item).strip()]
                    if not reasons:
                        reasons = None
                else:
                    reasons = None
                cost_flag = result.get("cost_covered_after")
                if cost_flag is not None:
                    cost_flag = bool(cost_flag)
                reason = str(result.get("reason", reasons[0] if reasons else ""))
                return DecisionResult(
                    action=action,
                    quantity=quantity,
                    confidence=confidence,
                    reason=reason,
                    raw=result,
                    price_hint=price_hint,
                    reasons=reasons,
                    cost_covered_after=cost_flag,
                )
            except Exception as exc:  # pragma: no cover - retry path
                last_error = exc
                attempt += 1
                if attempt > self.max_retries:
                    break
                time.sleep(self.retry_delay)
        raise LLMError(f"decide_action failed after {self.max_retries + 1} attempts: {last_error}")

    def _decide_with_state(
        self,
        structure_state: StructureState,
        position_state: PositionState,
        cfg: Any,
    ) -> Dict[str, Any]:
        context = build_ai_context(structure_state, position_state, cfg)
        decision = self._decide_from_context(context, schema=ACTION_SCHEMA)

        instruction = {
            "action": str(decision.action).upper(),
            "quantity": max(0.0, float(decision.quantity)),
            "reason": decision.reason,
            "confidence": float(decision.confidence),
        }
        valid, errors = validate_ai_instruction(instruction, position_state, cfg)

        return {
            "instruction": instruction,
            "valid": valid,
            "errors": errors,
            "context": context,
            "raw": decision.raw,
        }

    def decide_action(self, *args, **kwargs):  # type: ignore[override]
        if len(args) == 1 and isinstance(args[0], dict):
            context = args[0]
            schema = kwargs.get("schema")
            return self._decide_from_context(context, schema=schema)

        if len(args) == 3:
            structure_state, position_state, cfg = args
            return self._decide_with_state(structure_state, position_state, cfg)

        raise TypeError("decide_action expects either (context) or (structure_state, position_state, cfg)")

    def verify_segment_end(self, context: Dict[str, Any]) -> Dict[str, Any]:
        response = self.structure_llm.verify_segment_end(context)
        return {"segment_end": response}

    def assess_fugue(self, context: Dict[str, Any]) -> Dict[str, Any]:
        response = self.structure_llm.summarize_fugue(context)
        return {"fugue_state": response}

    def interpret_momentum(self, context: Dict[str, Any]) -> Dict[str, Any]:
        response = self.structure_llm.interpret_momentum(context)
        return {"momentum": response}

    def explain_signal(self, context: Dict[str, Any]) -> str:
        prompt = "Explain the following ChanLun signal in plain language:\n" + json.dumps(context, ensure_ascii=False, indent=2)
        return self.client.ask_text(prompt)

    def plan_decision(
        self,
        *,
        minutes_elapsed: int,
        structure_json: str,
        momentum_json: str,
        fusion_json: str,
        account_json: str,
        constraints_text: str,
        ta_json: str,
        performance_json: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> PlanDecisionResult:
        prompt_parts = [
            f"Minutes elapsed: {minutes_elapsed}",
            "Structure:" + structure_json.strip(),
            "Momentum:" + momentum_json.strip(),
            "Fusion:" + fusion_json.strip(),
            "Account:" + account_json.strip(),
            "Constraints:" + constraints_text.strip(),
            "TA:" + ta_json.strip(),
            "Performance:" + performance_json.strip(),
        ]
        prompt = "\n\n".join(part for part in prompt_parts if part)
        raw = self.client.ask_json(prompt, schema=schema)
        decisions_raw = raw.get("decisions") if isinstance(raw, dict) else None
        if isinstance(decisions_raw, list):
            decisions = [item for item in decisions_raw if isinstance(item, dict)]
        else:
            decisions = []
        notes = str(raw.get("notes", "")) if isinstance(raw, dict) else ""
        return PlanDecisionResult(decisions=decisions, notes=notes, raw=raw if isinstance(raw, dict) else {"content": raw})

    def short_explain(
        self,
        *,
        explanation_context: str,
        invalidate_hint: str,
    ) -> str:
        prompt = explanation_context.strip() + "\nInvalidate hint: " + invalidate_hint.strip()
        return self.client.ask_text(prompt)

    def stage_memory(
        self,
        *,
        memory_context: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> StageMemoryResult:
        prompt = "Stage memory context:\n" + memory_context.strip()
        raw = self.client.ask_json(prompt, schema=schema)
        stage_after = None
        cb_snapshot = None
        next_milestone = None
        if isinstance(raw, dict):
            stage_value = raw.get("stage_after")
            if isinstance(stage_value, str) and stage_value:
                stage_after = stage_value
            snapshot_value = raw.get("cb_snapshot")
            if isinstance(snapshot_value, dict):
                cb_snapshot = snapshot_value
            milestone_value = raw.get("next_milestone")
            if isinstance(milestone_value, dict):
                next_milestone = milestone_value
        return StageMemoryResult(stage_after=stage_after, cb_snapshot=cb_snapshot, next_milestone=next_milestone, raw=raw if isinstance(raw, dict) else {"content": raw})
