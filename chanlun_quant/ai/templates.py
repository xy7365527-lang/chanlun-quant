VERIFY_SEGMENT_END_JSON = """\
You are a ChanLun structure reviewer.
Return JSON only.

Input:
{context}

JSON:
{{
  "end_confirmed": true | false,
  "confidence": 0.0~1.0,
  "reason": "short justification"
}}
"""


MULTI_LEVEL_FUGUE_JSON = """\
You are a ChanLun multi-level analyst.
Return JSON only.

Input:
{context}

JSON:
{{
  "state": "resonance|hedge|dislocation",
  "direction": "up|down|flat",
  "score": 0.0~1.0,
  "action": "buy|sell|hold|lighten|observe",
  "reason": "short"
}}
"""


MOMENTUM_INTERPRET_JSON = """\
You are a ChanLun momentum interpreter focusing on MACD/EMA.
Return JSON only.

Input:
{context}

JSON:
{{
  "momentum_state": "strengthening|weakening|neutral",
  "bias": "bullish|bearish|neutral",
  "divergence": true|false,
  "confidence": 0.0~1.0,
  "reason": "short"
}}
"""


POST_DIVERGENCE_JSON = """\
You are a ChanLun analyst reviewing post-divergence evolution.
Return JSON only.

Input:
{context}

JSON:
{{
  "path": "consolidation|central_extension|new_trend|uncertain",
  "confidence": 0.0~1.0,
  "direction": "up|down|null",
  "reason": "short"
}}
"""


DECIDE_ACTION_JSON = """\
You are a ChanLun trading assistant.
Given structure, position, and extras, recommend one action.
Return JSON only.

Input:
{context}

JSON:
{{
  "action": "buy|sell|hold|reduce|exit",
  "quantity": 0.0,
  "price_hint": null | float,
  "confidence": 0.0~1.0,
  "reason": "short"
}}
"""
