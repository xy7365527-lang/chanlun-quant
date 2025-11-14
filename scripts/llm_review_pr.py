# Create PR review script
from __future__ import annotations

import os
import sys
from pathlib import Path
from textwrap import dedent

import requests

MAX_DIFF_BYTES = 150_000
OUTPUT_FILE = Path("review_result.txt")
DIFF_FILE = Path("pr.diff")

PROMPT_TEMPLATE = dedent(
    """
    你是一位资深的 Python 代码审查专家，专注于量化交易系统的代码质量。

    请对以下 Git diff 进行全面审查，重点关注：

    ## 审查维度
    1. **安全性与边界条件**
       - 数值计算是否有除零、溢出风险
       - 数组索引是否可能越界
       - 空值/None 的处理是否完善

    2. **代码质量**
       - 复杂度是否过高
       - 命名是否清晰
       - 是否有重复代码

    3. **潜在 Bug**
       - 逻辑错误
       - 类型不匹配
       - 资源泄漏

    4. **性能与优化**
       - 是否有不必要的循环或计算
       - 数据结构选择是否合理

    5. **测试覆盖**
       - 是否需要补充测试用例
       - 边界条件是否有测试

    ## 输出格式
    请用中文输出，格式如下：

    ### ✅ 审查通过的部分
    - [简要说明好的实践]

    ### ⚠️ 需要注意的问题
    **文件: `路径/文件名.py`**
    - 行 X: [具体问题描述]
      - 建议: [改进建议]

    ### 🔧 可选优化建议
    - [性能或代码质量改进建议]

    ## DIFF 内容
    ```diff
    {diff}
    ```
    """
)


def load_diff() -> str:
    try:
        diff_text = DIFF_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"❌ 未找到 diff 文件: {DIFF_FILE}")
        raise SystemExit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ 读取 diff 失败: {exc}")
        raise SystemExit(0)

    diff_text = diff_text[:MAX_DIFF_BYTES]
    if not diff_text.strip():
        print("ℹ️ 无代码变更，跳过审查")
        raise SystemExit(0)
    return diff_text


def build_prompt(diff: str) -> str:
    return PROMPT_TEMPLATE.format(diff=diff)


def call_codex(prompt: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ 未设置 OPENAI_API_KEY")
        raise SystemExit(0)

    payload = {
        "model": "code-davinci-002",
        "prompt": prompt,
        "temperature": 0.2,
        "max_tokens": 2000,
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["text"].strip()
    except Exception as exc:  # noqa: BLE001
        fallback = (
            "⚠️ LLM 审查服务暂时不可用: "
            f"{exc}\n\n请人工审查代码变更。"
        )
        OUTPUT_FILE.write_text(fallback, encoding="utf-8")
        print(fallback)
        raise SystemExit(0)


def write_output(content: str) -> None:
    OUTPUT_FILE.write_text(content, encoding="utf-8")
    print("✅ 审查完成")
    print(content[:500])


def main() -> None:
    diff_text = load_diff()
    prompt = build_prompt(diff_text)
    review = call_codex(prompt)
    write_output(review)


if __name__ == "__main__":
    main()
