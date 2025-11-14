"""
Minimal HTTP backends for LLM providers.

当前仅实现兼容 OpenAI Chat Completions API 的后台。其他 provider 可扩展此模块。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


class BackendError(RuntimeError):
    pass


@dataclass
class OpenAICompatibleBackend:
    api_key: str
    api_base: str = "https://api.openai.com"
    timeout: float = 30.0

    def _endpoint(self) -> str:
        base = self.api_base.rstrip("/")
        return f"{base}/v1/chat/completions"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def ask_json(self, prompt: str, *, model: str, temperature: float, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a trading assistant that must reply in JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
        }
        if schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": schema,
                },
            }

        response = requests.post(
            self._endpoint(),
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise BackendError(f"OpenAI error {response.status_code}: {response.text}")
        data = response.json()
        try:
            message = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise BackendError(f"Malformed OpenAI response: {data}") from exc
        try:
            return json.loads(message)
        except json.JSONDecodeError as exc:
            raise BackendError(f"OpenAI response is not valid JSON: {message}") from exc

    def ask_text(self, prompt: str, *, model: str, temperature: float) -> str:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a trading assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
        }
        response = requests.post(
            self._endpoint(),
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise BackendError(f"OpenAI error {response.status_code}: {response.text}")
        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise BackendError(f"Malformed OpenAI response: {data}") from exc


def create_backend(provider: str, *, api_base: str, api_key: str, timeout: float = 30.0):
    normalized = provider.lower()
    if normalized in {"openai", "openai-compatible"}:
        if not api_key:
            raise BackendError("OpenAI backend requires api_key")
        return OpenAICompatibleBackend(api_key=api_key, api_base=api_base or "https://api.openai.com", timeout=timeout)
    raise BackendError(f"Unsupported LLM provider: {provider}")


__all__ = ["create_backend", "OpenAICompatibleBackend", "BackendError"]

