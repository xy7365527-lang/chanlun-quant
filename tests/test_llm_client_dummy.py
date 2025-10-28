from chanlun_quant.ai.interface import ChanLLM
from chanlun_quant.ai.client import JsonLLMClient

class DummyLLM(JsonLLMClient):
    def __init__(self):
        super().__init__(endpoint="http://dummy")

    def ask_json(self, prompt, schema):
        return {"proposals": [{"bucket": "segment", "action": "SELL", "size_delta": 50, "refs": ["seg_M15_0"], "methods": ["divergence"], "why": "dummy"}]}

def test_dummy_llm_injection():
    llm = ChanLLM(client=DummyLLM())
    assert hasattr(llm, "client")
