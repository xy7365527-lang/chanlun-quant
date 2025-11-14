from __future__ import annotations

FUGUE_DECISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "directives": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "bucket": {"type": "string", "enum": ["pen", "segment"]},
                    "action": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
                    "size_delta": {"type": "number", "minimum": 0},
                    "price_band": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 2,
                        "items": {"type": "number"},
                    },
                    "refs": {"type": "array", "items": {"type": "string"}},
                    "methods": {"type": "array", "items": {"type": "string"}},
                    "narrative": {"type": "string", "maxLength": 200},
                },
                "required": ["bucket", "action", "size_delta", "refs", "methods"],
            },
        }
    },
    "required": ["directives"],
}

FEWSHOTS = r"""
[Example 1]
context: 低级别 M15 段出现 'divergence+3sell'，上级 H1 仍在上行趋势带。
decision:
{"directives":[
  {"bucket":"segment","action":"SELL","size_delta":120,"price_band":[101.2,101.8],
   "refs":["seg_M15_42"],"methods":["divergence","mmd","zhongshu"],"narrative":"低级段背驰兑现，用于成本归零"},
  {"bucket":"pen","action":"BUY","size_delta":60,"price_band":[99.6,100.3],
   "refs":["pen_M15_180"],"methods":["zhongshu"],"narrative":"中枢下半区回补做T"}
]}

[Example 2]
context: H1 出现 '2buy' 离开，M15 回踩上沿；净方向 long。
decision:
{"directives":[
  {"bucket":"segment","action":"BUY","size_delta":100,"price_band":[203.5,204.0],
   "refs":["seg_H1_9"],"methods":["mmd","zhongshu"],"narrative":"2buy 离开，轻加"},
  {"bucket":"pen","action":"SELL","size_delta":40,"price_band":[205.2,205.8],
   "refs":["pen_M15_311"],"methods":["zhongshu"],"narrative":"上半区减T，保持净多"}
]}
"""

FUGUE_DECISION_PROMPT = """
你是 Fugue Conductor（通用多级指挥器）。
数据：<CONTEXT/> 给出多级结构摘要（segments/pens）与预信号（pre_signals）。
目标：在不改变 envelope.net_direction 的前提下，组织“单周期一组净指令”，优先兑现抵减 remaining_cost。
必须遵守：
- pen：仅中枢内 T+0；segment：段级兑现/轻加；不得改变净方向；
- 所有指令需要 refs（结构 id）与 methods（证据标签）；
- 仅输出 JSON（FUGUE_DECISION_SCHEMA）；不得输出解释文字。
策略提示：
- 若预信号出现“divergence+3sell”类型 → 优先给 segment SELL；
- 若中枢跨度可覆盖费用阈 → pen 给成对的 BUY/SELL；
- 若特征序列不唯一或证据不足 → HOLD。
Few-shots:
{fewshots}
<CONTEXT>
{context}
</CONTEXT>
仅输出 JSON。
"""

