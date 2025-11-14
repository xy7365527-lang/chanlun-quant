from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .templates import (
    DECIDE_ACTION_JSON,
    MOMENTUM_INTERPRET_JSON,
    MULTI_LEVEL_FUGUE_JSON,
    POST_DIVERGENCE_JSON,
    ROUND_A_PROMPT,
    ROUND_B_DECISION_SCHEMA,
    ROUND_C_BRIEF_PROMPT,
    ROUND_D_MEMORY_PROMPT,
    SYSTEM_BASE_PROMPT,
    VERIFY_SEGMENT_END_JSON,
)


class LLMError(RuntimeError):
    pass


class LLMClient:
    """Thin wrapper around a backend that can answer JSON prompts."""

    def __init__(
        self,
        provider: str = "mock",
        model: str = "gpt-4",
        temperature: float = 0.0,
        *,
        backend: Optional[Any] = None,
        mock_response: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self._backend = backend
        self._mock_response = mock_response or {"action": "hold", "reason": "mock"}

        if provider != "mock" and backend is None:
            raise ValueError("Non-mock provider requires a backend")

    def ask_json(self, prompt: str, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.provider == "mock":
            return dict(self._mock_response)

        if not self._backend:
            raise LLMError("No backend configured")

        try:
            response = self._backend.ask_json(prompt, model=self.model, temperature=self.temperature, schema=schema)
        except Exception as exc:  # pragma: no cover
            raise LLMError(f"LLM backend error: {exc}") from exc

        if not isinstance(response, dict):
            raise LLMError("LLM response must be dict")
        return response

    def ask_text(self, prompt: str) -> str:
        if self.provider == "mock":
            if isinstance(self._mock_response, dict):
                return str(self._mock_response.get("reason", "mock"))
            return str(self._mock_response)

        if not self._backend:
            raise LLMError("No backend configured")

        if hasattr(self._backend, "ask_text"):
            try:
                response = self._backend.ask_text(prompt, model=self.model, temperature=self.temperature)
            except Exception as exc:  # pragma: no cover
                raise LLMError(f"LLM backend error: {exc}") from exc
            return response if isinstance(response, str) else str(response)

        try:
            fallback = self._backend.ask_json(prompt, model=self.model, temperature=self.temperature)
        except Exception as exc:  # pragma: no cover
            raise LLMError(f"LLM backend error: {exc}") from exc
        if isinstance(fallback, dict):
            return json.dumps(fallback, ensure_ascii=False)
        return str(fallback)


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
        self.client = client or LLMClient()

    def _ask_json(
        self,
        template: str,
        context: Dict[str, Any],
        *,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context_json = json.dumps(context, ensure_ascii=False, indent=2)
        prompt = template.replace("{context}", context_json)
        return self.client.ask_json(prompt, schema=schema)

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
    """High level trading advisor using StructureLLM."""

    def __init__(
        self,
        *,
        structure_llm: Optional[StructureLLM] = None,
        client: Optional[LLMClient] = None,
        max_retries: int = 0,
        retry_delay: float = 0.5,
    ) -> None:
        if structure_llm:
            self.structure_llm = structure_llm
        else:
            self.structure_llm = StructureLLM(client)
        self.max_retries = max(0, max_retries)
        self.retry_delay = max(retry_delay, 0.0)

    def decide_action(
        self,
        context: Dict[str, Any],
        *,
        schema: Optional[Dict[str, Any]] = None,
    ) -> DecisionResult:
        attempt = 0
        last_error: Optional[Exception] = None
        while attempt <= self.max_retries:
            try:
                result = self.structure_llm._ask_json(DECIDE_ACTION_JSON, context, schema=schema)
                action = str(result.get("action", "hold"))
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
                if isinstance(reasons_raw, list):
                    reasons_list = [str(item) for item in reasons_raw if str(item).strip()]
                    if not reasons_list:
                        reasons_list = None
                else:
                    reasons_list = None
                cost_flag = result.get("cost_covered_after")
                if cost_flag is not None:
                    cost_flag = bool(cost_flag)
                reason = str(result.get("reason", reasons_list[0] if reasons_list else ""))
                return DecisionResult(
                    action=action,
                    quantity=quantity,
                    confidence=confidence,
                    reason=reason,
                    raw=result,
                    price_hint=price_hint,
                    reasons=reasons_list,
                    cost_covered_after=cost_flag,
                )
            except Exception as exc:
                last_error = exc
                attempt += 1
                if attempt > self.max_retries:
                    break
                time.sleep(self.retry_delay)
        raise LLMError(f"decide_action failed after {self.max_retries + 1} attempts: {last_error}")

    # ------------------------------------------------------------------
    # Multi-round structured interactions
    # ------------------------------------------------------------------
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
        """Execute the decision planning round using the structured prompt pack."""

        prompt_parts = [
            SYSTEM_BASE_PROMPT.strip(),
            ROUND_A_PROMPT.format(
                minutes_elapsed=minutes_elapsed,
                structure_json=structure_json.strip(),
                momentum_json=momentum_json.strip(),
                fusion_json=fusion_json.strip(),
                account_json=account_json.strip(),
                constraints_text=constraints_text.strip(),
                ta_json=ta_json.strip(),
                performance_json=performance_json.strip(),
            ).strip(),
            ROUND_B_DECISION_SCHEMA.strip(),
        ]
        prompt = "\n\n".join(part for part in prompt_parts if part)
        raw = self.structure_llm.client.ask_json(prompt, schema=schema)

        decisions_data = raw.get("decisions") if isinstance(raw, dict) else None
        if isinstance(decisions_data, list):
            decisions = [item for item in decisions_data if isinstance(item, dict)]
        else:
            decisions = []
        notes = ""
        if isinstance(raw, dict) and "notes" in raw:
            notes = str(raw.get("notes", ""))
        return PlanDecisionResult(decisions=decisions, notes=notes, raw=raw)

    def short_explain(
        self,
        *,
        explanation_context: str,
        invalidate_hint: str,
    ) -> str:
        """Produce a concise textual explanation for logging/audit purposes."""

        prompt_parts = [
            SYSTEM_BASE_PROMPT.strip(),
            explanation_context.strip(),
            ROUND_C_BRIEF_PROMPT.format(invalidate_hint=invalidate_hint).strip(),
        ]
        prompt = "\n\n".join(part for part in prompt_parts if part)
        return self.structure_llm.client.ask_text(prompt)

    def stage_memory(
        self,
        *,
        memory_context: str,
        schema: Optional[Dict[str, Any]] = None,
    ) -> StageMemoryResult:
        """Collect structured memory about cost-progress stages."""

        prompt_parts = [
            SYSTEM_BASE_PROMPT.strip(),
            memory_context.strip(),
            ROUND_D_MEMORY_PROMPT.strip(),
        ]
        prompt = "\n\n".join(part for part in prompt_parts if part)
        raw = self.structure_llm.client.ask_json(prompt, schema=schema)

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

        return StageMemoryResult(
            stage_after=stage_after,
            cb_snapshot=cb_snapshot,
            next_milestone=next_milestone,
            raw=raw,
        )

