from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests

LOGGER = logging.getLogger(__name__)


class RESTTradingAgentAdapter:
    """
    简单的 REST adapter，向外部研究服务 POST JSON，并返回解析后的结果。

    期望外部服务遵循如下接口：
      - URL: {base_url}/research
      - Header: Authorization: Bearer <api_key> （如果提供）
      - Body: 传入 ResearchRequest.to_dict() 结构
      - Response: JSON，可直接传给 TradingAgentsManager._parse_packet
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _endpoint(self) -> str:
        return f"{self.base_url}/research"

    def generate(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            response = requests.post(
                self._endpoint(),
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                LOGGER.warning("REST adapter返回非 JSON 对象: %s", data)
                return None
            return data
        except Exception as exc:
            LOGGER.warning("REST adapter调用失败: %s", exc)
            return None


__all__ = ["RESTTradingAgentAdapter"]

