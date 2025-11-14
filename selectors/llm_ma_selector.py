from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import pandas as pd
import json
import math
import logging

from chanlun_quant.indicators.ma_system import ma_system_features, DEFAULT_PERIODS

logger = logging.getLogger(__name__)


@dataclass
class SelectorConfig:
    frequencys: List[str]
    candidate_selector: Optional[str]
    max_candidates: int
    ma_periods: List[int]
    require_fields: List[str]
    llm_model: Optional[str]
    llm_json_strict: bool
    top_k: int
    min_score: float
    enforce_gate: bool = True
    enforce_veto: bool = True


class LLMMASelector:
    """
    多维特征 -> TradingAgents 评分 -> 缠论最终裁决 -> 1~2 标的 + 指令
    """

    def __init__(self, deps: Dict[str, Any], config: Dict[str, Any]):
        self.mk_datas = deps.get("market_datas")
        self.agents = deps.get("agents")  # AgentsAdapter
        self.candidate_runner = deps.get("candidate_runner")
        self.fundamentals = deps.get("fundamentals")

        self.cfg = SelectorConfig(
            frequencys=config.get("frequencys", ["d"]),
            candidate_selector=config.get("candidate_selector"),
            max_candidates=int(config.get("max_candidates", 60)),
            ma_periods=config.get("ma_periods", DEFAULT_PERIODS),
            require_fields=config.get("require_fields", ["pe", "market_cap", "sector"]),
            llm_model=config.get("llm_model"),
            llm_json_strict=bool(config.get("llm_json_strict", True)),
            top_k=int(config.get("top_k", 2)),
            min_score=float(config.get("min_score", 0.0)),
            enforce_gate=bool(config.get("enforce_gate", True)),
            enforce_veto=bool(config.get("enforce_veto", True)),
        )

        if self.agents is None:
            raise RuntimeError("deps['agents'] 未注入（需要 AgentsAdapter 实例）")
        if self.mk_datas is None:
            raise RuntimeError("deps['market_datas'] 未注入（需要 MarketDatas 实例）")

    # -------------------------
    # 工具：安全获取 df / cl_data
    # -------------------------
    def _get_kline_df(self, code: str, freq: str, as_of=None) -> Optional[pd.DataFrame]:
        try:
            df = self.mk_datas.get_kline_df(code, freq, end_date=as_of)
        except TypeError:
            df = self.mk_datas.get_kline_df(code, freq)
        if df is None or len(df) == 0:
            return None
        # 若 df 带 date 且 as_of 提供，则截断
        if as_of is not None:
            for col in ("date", "datetime", "time"):
                if col in df.columns:
                    try:
                        cutoff = pd.Timestamp(as_of)
                        df = df[df[col] <= cutoff]
                    except Exception:
                        pass
                    break
        return df

    def _get_cl_data(self, code: str, freq: str, as_of=None):
        try:
            return self.mk_datas.get_cl_data(code, freq, end_date=as_of)
        except TypeError:
            return self.mk_datas.get_cl_data(code, freq)

    # -------------------------
    # 特征抽取（均线/缠论/MACD/基本面）
    # -------------------------
    def _fetch_features_for_code(self, code: str, freq: str, as_of=None) -> Dict[str, Any]:
        kdf = self._get_kline_df(code, freq, as_of=as_of)
        if kdf is None or len(kdf) < max(self.cfg.ma_periods) + 5:
            return {}

        ma_state = ma_system_features(kdf, self.cfg.ma_periods)

        cd = self._get_cl_data(code, freq, as_of=as_of)
        bis = cd.get_bis() if hasattr(cd, "get_bis") else []
        zss = cd.get_bi_zss() if hasattr(cd, "get_bi_zss") else []
        last_bi = bis[-1] if bis else None

        def _has(bi, names):
            try:
                return bi.mmd_exists(names, "|")
            except Exception:
                return False

        def _has_bc(bi, names):
            try:
                return bi.bc_exists(names, "|")
            except Exception:
                return False

        chan_summary = {
            "last_bi_dir": getattr(last_bi, "type", None),
            "has_1buy": _has(last_bi, ["1buy"]) if last_bi else False,
            "has_2buy": _has(last_bi, ["2buy"]) if last_bi else False,
            "has_3buy": _has(last_bi, ["3buy"]) if last_bi else False,
            "has_pz_bc": _has_bc(last_bi, ["pz"]) if last_bi else False,
            "has_qs_bc": _has_bc(last_bi, ["qs"]) if last_bi else False,
            "zs_count": len(zss),
        }

        idx = cd.get_idx() if hasattr(cd, "get_idx") else {}
        macd = idx.get("macd", {})
        macd_summary = {
            "dif": float(macd.get("dif", [-math.inf])[-1]) if macd else None,
            "dea": float(macd.get("dea", [-math.inf])[-1]) if macd else None,
            "hist": float(macd.get("hist", [-math.inf])[-1]) if macd else None,
        }

        fundamentals = {}
        if self.fundamentals:
            try:
                fundamentals = self.fundamentals(code) or {}
            except Exception:
                fundamentals = {}
        for f in self.cfg.require_fields:
            fundamentals.setdefault(f, None)

        # 缠论硬门槛（只要任一买点或背驰 + 均线至少不差 + 非向下发散）
        pass_gate = (
            (chan_summary["has_1buy"] or chan_summary["has_2buy"] or chan_summary["has_3buy"]
             or chan_summary["has_pz_bc"] or chan_summary["has_qs_bc"])
            and (ma_state.bull_alignment or ma_state.strength_category >= 5)
            and (not ma_state.diverge_down)
        )

        # 红线（最终裁决用）
        red_flags = (ma_state.bear_alignment or ma_state.diverge_down)

        feat = {
            "symbol": code,
            "freq": freq,
            "ma_system": {
                "bull_alignment": ma_state.bull_alignment,
                "bear_alignment": ma_state.bear_alignment,
                "glue": ma_state.glue,
                "diverge_up": ma_state.diverge_up,
                "diverge_down": ma_state.diverge_down,
                "resist_levels": ma_state.resist_levels,
                "support_levels": ma_state.support_levels,
                "strength_category": ma_state.strength_category,
                "snapshot": ma_state.snapshot,
            },
            "chan": {
                **chan_summary,
                "pass_gate": pass_gate,
                "red_flags": red_flags,
            },
            "indicators": {"macd": macd_summary},
            "fundamentals": fundamentals,
        }
        return feat

    # -------------------------
    # Prompt（JSON-only，强调缠论硬约束）
    # -------------------------
    def _build_prompt(self, stock_feature_list: List[Dict[str, Any]]) -> str:
        rules = (
            "你是多智能体投研协调器。严格遵守：\n"
            "R1 仅对 pass_gate=true 的股票评分；\n"
            "R2 凡 red_flags=true 或与缠论红线冲突，禁止给出“买入”，仅“观察/忽略”；\n"
            "R3 严格 JSON 输出，无任何多余文本；\n"
            "R4 从分析对象中推荐 1–2 只 top_picks。\n"
        )
        schema = (
            "{\n"
            '  "analysis":[{"symbol":"...","score":0.0,"recommendation":"买入|观察|忽略","reason":"…"}],\n'
            '  "top_picks":["代码1","代码2"]\n'
            "}\n"
        )
        scoring = (
            "评分参考：缠论买点(3>2>1)、盘整/趋势背驰转强、多头排列/向上发散、"
            "MACD(零轴上方扩张)、板块与估值。"
        )
        payload = {"stocks": stock_feature_list}
        return f"{rules}\n输出模板：\n{schema}\n评分要点：{scoring}\n输入数据(JSON)：\n" \
               + json.dumps(payload, ensure_ascii=False)

    def _call_agents(self, prompt: str) -> Dict[str, Any]:
        params = {}
        if self.cfg.llm_model:
            params["model"] = self.cfg.llm_model
        return self.agents.ask_json(prompt, **params)

    # -------------------------
    # 最终缠论裁决（红线否决/降级）
    # -------------------------
    def _apply_chan_veto(self, top_picks: List[str], feat_map: Dict[str, Dict[str, Any]]) -> List[str]:
        ok = []
        for s in top_picks:
            f = feat_map.get(s, {})
            chan = f.get("chan", {})
            if chan.get("red_flags"):
                # 否决：不加入最终 picks
                continue
            ok.append(s)
        return ok

    # -------------------------
    # 主入口
    # -------------------------
    def select(self, as_of=None) -> Dict[str, Any]:
        # 1) 候选池
        if self.candidate_runner:
            candidates = self.candidate_runner(self.mk_datas, self.cfg.frequencys, as_of)
        else:
            # 兜底：直接从市场池截取
            candidates = getattr(self.mk_datas, "codes", []) or []
        candidates = candidates[: self.cfg.max_candidates]

        if not candidates:
            return {"symbols": [], "data": None, "meta": {"reason": "no candidates"}}

        # 2) 特征 + 硬门槛过滤
        freq = self.cfg.frequencys[0]
        feats_all: List[Dict[str, Any]] = []
        feats: List[Dict[str, Any]] = []
        for code in candidates:
            try:
                f = self._fetch_features_for_code(code, freq, as_of=as_of)
                if not f:
                    continue
                feats_all.append(f)
                if (not self.cfg.enforce_gate) or f["chan"]["pass_gate"]:
                    feats.append(f)
            except Exception as e:
                logger.exception("build features failed for %s: %s", code, e)

        if not feats:
            return {"symbols": [], "data": None, "meta": {"reason": "no pass_gate candidates"}}

        # 3) Agents 决策
        prompt = self._build_prompt(feats)
        resp = self._call_agents(prompt)

        analysis = resp.get("analysis", [])
        df = pd.DataFrame(analysis) if analysis else pd.DataFrame()
        if not df.empty and "score" in df.columns:
            df = df.sort_values("score", ascending=False)
            df = df[df["score"] >= self.cfg.min_score].reset_index(drop=True)

        # 4) 取 top_picks（无则按得分取前 top_k）
        top_picks = resp.get("top_picks", []) or []
        if (not top_picks) and (not df.empty):
            top_picks = df.head(self.cfg.top_k)["symbol"].tolist()

        # 5) 缠论最终裁决
        feat_map = {f["symbol"]: f for f in feats_all}
        final_picks = top_picks
        if self.cfg.enforce_veto:
            final_picks = self._apply_chan_veto(top_picks, feat_map)

        # 交易指令：红线 → 观察；其余按推荐，final_picks → 买入
        trade = []
        topset = set(final_picks)
        for _, row in df.iterrows():
            sym = row["symbol"]
            chan = feat_map.get(sym, {}).get("chan", {})
            action = "观察"
            if sym in topset:
                action = "买入"
            elif chan.get("red_flags"):
                action = "观察"
            else:
                # 采用模型建议
                action = row.get("recommendation") or "观察"
            trade.append({
                "symbol": sym,
                "action": action,
                "score": float(row.get("score", 0)),
                "reason": row.get("reason", "")
            })
        trade_df = pd.DataFrame(trade) if trade else None

        return {
            "symbols": final_picks[: self.cfg.top_k],
            "data": trade_df,
            "meta": {
                "strategy": "TA_MA_Selector",
                "freq": freq,
                "candidates": len(candidates),
                "pass_gate": sum(1 for f in feats if f["chan"]["pass_gate"]) if feats else 0,
                "picked": len(final_picks),
                "as_of": str(as_of) if as_of else "latest"
            }
        }


def build(deps: Dict[str, Any], config: Dict[str, Any] = None):
    return LLMMASelector(deps, config or {})
