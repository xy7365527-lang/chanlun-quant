# -*- coding: utf-8 -*-
import pandas as pd

from chanlun_quant.selectors.llm_ma_selector import LLMMASelector


class DummyMarket:
    codes = ["AAA", "BBB"]

    def get_kline_df(self, code, freq, end_date=None):
        import numpy as np

        n = 300
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        base = 100 + np.arange(n) * 0.1
        df = pd.DataFrame(
            {
                "date": dates,
                "open": base,
                "high": base + 0.3,
                "low": base - 0.3,
                "close": base,
                "volume": np.full(n, 1000),
            }
        )
        return df

    def get_cl_data(self, code, freq, end_date=None):
        class DummyBI:
            type = "down"

            def mmd_exists(self, names, *_):
                return "1buy" in names

            def bc_exists(self, names, *_):
                return False

        class DummyCD:
            def get_bis(self):
                return [DummyBI()]

            def get_bi_zss(self):
                return []

            def get_idx(self):
                return {"macd": {"dif": [0.2], "dea": [0.15], "hist": [0.05]}}

        return DummyCD()


class DummyAgents:
    def ask_json(self, prompt, **kwargs):
        return {
            "analysis": [
                {"symbol": "AAA", "score": 0.9, "recommendation": "买入", "reason": "good"},
                {"symbol": "BBB", "score": 0.8, "recommendation": "买入", "reason": "ok"},
            ],
            "top_picks": ["AAA", "BBB"],
        }


def test_selector_gate_and_veto():
    deps = {
        "market_datas": DummyMarket(),
        "agents": DummyAgents(),
        "candidate_runner": lambda mk, freqs, as_of: ["AAA", "BBB"],
        "fundamentals": lambda code: {},
    }
    selector = LLMMASelector(deps, {"frequencys": ["d"], "max_candidates": 10, "top_k": 2})
    result = selector.select()
    assert result["symbols"], "Expected at least one pick"
    assert result["data"] is not None
