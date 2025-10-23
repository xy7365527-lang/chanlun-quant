"""Prompt templates for LLM (JSON Only)."""

# 线段终结核验（JSON Only）
VERIFY_SEGMENT_END_JSON = """\
You are a ChanLun (缠论) structure verifier.
Task: Decide whether the current segment should END based on feature-sequence context.
Constraints: JSON only. No prose.

Input:
{context}

Output JSON (keys):
{{
  "segment_end": true|false,
  "confidence": 0.0~1.0,
  "reason": "short chinese explanation"
}}
"""

# 信号解释（短文）
EXPLAIN_SIGNAL_CN_TEXT = """\
你是一名缠论讲解员，请用中文给出简洁解释（不超过120字）。
输入结构：
{context}

输出：一段中文简述，说明该信号的缠论含义与风险要点。
"""

# 多级别赋格评估（JSON Only）
MULTI_LEVEL_FUGUE_JSON = """\
You are a multi-timeframe fusion analyst.
Given the latest signals per level and resonance matrix, output JSON only.

Input:
{context}

Expected JSON:
{{
  "fugue_state": "共振|对冲|错位",
  "score": 0.0~1.0,
  "confidence": 0.0~1.0,
  "action": "顺势做多|观望|减仓|反手",
  "reason": "short"
}}
"""

# 动能解读（JSON Only）
MOMENTUM_INTERPRET_JSON = """\
You are a momentum interpreter for MACD/EMA.
Return JSON only, no prose.

Input:
{context}

JSON:
{{
  "momentum": "增强|衰减|不明",
  "confidence": 0.0~1.0,
  "reason": "short"
}}
"""

# 行动决策（JSON Only；与 ACTION_SCHEMA 对齐）
DECIDE_ACTION_JSON = """\
You are an execution planner following ChanLun rules + cost-reduction rhythm.
Read the context and output ONLY JSON (no prose) that conforms to given schema:
- action: "BUY"|"SELL"|"HOLD"
- quantity: number >= 0
- leverage: optional number >= 0
- reason: short string

Context:
{context}

JSON ONLY:
{{
  "action": "BUY|SELL|HOLD",
  "quantity": 0,
  "leverage": 0,
  "reason": "..."
}}
"""
