"""
最小化 LLM 调用脚本，用于验证 llm_provider / llm_api_* 配置是否正确。

示例：
    CLQ_LLM_PROVIDER=openai CLQ_LLM_API_KEY=sk-xxx python -m script.llm_sanity
"""

from __future__ import annotations

import argparse
import json

from chanlun_quant.config import Config
from chanlun_quant.ai.interface import LLMClient, LLMError


def main() -> None:
    parser = argparse.ArgumentParser(description="测试 LLM 配置是否可以正常返回 JSON。")
    parser.add_argument(
        "--prompt",
        default="请仅返回 JSON 对象 {\"echo\": \"pong\"}，不要添加任何多余文字。",
        help="发送给模型的 prompt 内容。",
    )
    args = parser.parse_args()

    cfg = Config.from_env()
    client = LLMClient(
        provider=cfg.llm_provider,
        model=cfg.llm_model,
        temperature=cfg.llm_temperature,
        api_base=cfg.llm_api_base,
        api_key=cfg.llm_api_key,
        timeout=cfg.llm_request_timeout,
    )

    try:
        response = client.ask_json(args.prompt)
    except LLMError as exc:
        print("LLM 调用失败:", exc)
        raise SystemExit(1) from exc

    print("LLM 返回的 JSON:")
    print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

