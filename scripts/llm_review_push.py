# Create push review script
from __future__ import annotations

import os
from pathlib import Path
from textwrap import dedent

import requests

MAX_DIFF_BYTES = 150_000
OUTPUT_FILE = Path("review_result.txt")
DIFF_FILE = Path("commit.diff")
INFO_FILE = Path("commit_info.txt")

PROMPT_TEMPLATE = dedent(
    """
    你是一位资深的 Python 代码审查专家，专注于量化交易系统的代码质量。

    以下是本次提交的关键信息：
    {commit_info}

    请对下面的 Git diff 进行全面审查，重点关注：

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


def load_text(path: Path, default: str = "") -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ 读取 {path} 失败: {exc}")
        return default
    return content


def load_diff() -> str:
    diff = load_text(DIFF_FILE)
    diff = diff[:MAX_DIFF_BYTES]
    if not diff.strip():
        print("ℹ️ 无代码变更，跳过审查")
        raise SystemExit(0)
    return diff


def build_prompt(diff: str, info: str) -> str:
    info = info.strip() or "(无法读取提交信息)"
    return PROMPT_TEMPLATE.format(commit_info=info, diff=diff)


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
            f"{exc}\n\n提交概要:\n{load_text(INFO_FILE)}"
        )
        OUTPUT_FILE.write_text(fallback, encoding="utf-8")
        print(fallback)
        raise SystemExit(0)


def main() -> None:
    diff = load_diff()
    info = load_text(INFO_FILE)
    prompt = build_prompt(diff, info)
    review = call_codex(prompt)
    OUTPUT_FILE.write_text(review, encoding="utf-8")
    print("✅ 审查完成")
    print(review[:500])


if __name__ == "__main__":
    main()
