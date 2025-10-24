import argparse
import importlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import pandas as pd

# --- 项目内导入 ---
from chanlun_quant.agents.orchestrators.ta_orchestrator import TAOrchestrator, TAConfig
from chanlun_quant.agents.adapter import AgentsAdapter
from chanlun_quant.selectors.llm_ma_selector import build as build_selector

# 若你已经实现了候选池聚合器，可改为你的路径
try:
    from chanlun_quant.selectors.candidate_aggregator import merge_candidates as DEFAULT_CANDIDATE_RUNNER
except Exception:
    DEFAULT_CANDIDATE_RUNNER = None

logger = logging.getLogger("wire_ta_selector")
logging.basicConfig(
    level=os.environ.get("CLQ_LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


# -----------------------------
# 动态加载器工具
# -----------------------------
def load_callable(dotted: Optional[str]) -> Optional[Callable]:
    """
    加载 "module.path:attr" 的可调用对象；dotted 为 None 则返回 None
    """
    if not dotted:
        return None
    if ":" not in dotted:
        raise ValueError(f"Invalid dotted path (expect 'module:attr'): {dotted}")
    mod, attr = dotted.split(":", 1)
    m = importlib.import_module(mod)
    fn = getattr(m, attr)
    if not callable(fn):
        raise TypeError(f"Loaded object is not callable: {dotted}")
    return fn


# -----------------------------
# 读取 ENV / YAML 的参数
# -----------------------------
def build_ta_orchestrator(args) -> TAOrchestrator:
    """
    优先从 YAML 构造；否则从 ENV 构造。两者都允许完整 TradingAgents 参数注入。
    """
    # 你可以把 llm_client 注入 TAOrchestrator（如果你的 TA 需要共用已有 LLM 客户端）
    llm_client = None

    if args.ta_yaml:
        logger.info("Load TradingAgents config from YAML: %s", args.ta_yaml)
        orch = TAOrchestrator.from_yaml(args.ta_yaml, llm_client=llm_client)
    else:
        logger.info("Load TradingAgents config from ENV (prefix=CLQ_TA_)")
        orch = TAOrchestrator.from_env(prefix="CLQ_TA_", llm_client=llm_client)
    return orch


def build_market_datas() -> Any:
    """
    通过 ENV 指定 market_datas 工厂：CLQ_MKD_FACTORY = "module:make_market_datas"
    要求工厂函数返回对象，至少提供：
        - .codes : List[str]
        - .get_kline_df(code, freq, end_date=None) -> pd.DataFrame
        - .get_cl_data(code, freq, end_date=None) -> 缠论数据对象（需含 get_bis/get_bi_zss/get_idx）
    """
    factory_path = os.environ.get("CLQ_MKD_FACTORY")
    if not factory_path:
        raise RuntimeError(
            "未设置 CLQ_MKD_FACTORY（如 'your.module:make_market_datas'）。"
            "请提供一个能返回 market_datas 的工厂，满足 llm_ma_selector 的依赖接口。"
        )
    factory = load_callable(factory_path)
    mk_datas = factory()
    # 粗检
    missing = []
    if not hasattr(mk_datas, "codes"):
        missing.append("codes")
    if not hasattr(mk_datas, "get_kline_df"):
        missing.append("get_kline_df")
    if not hasattr(mk_datas, "get_cl_data"):
        missing.append("get_cl_data")
    if missing:
        raise TypeError(f"market_datas 缺少必须接口: {missing}")
    return mk_datas


def build_candidate_runner() -> Optional[Callable]:
    """
    候选池聚合器（可选）：CLQ_CANDIDATE_RUNNER = "module:merge_candidates"
    不设置则使用 llm_ma_selector 内部的兜底（从 mk_datas.codes 切前 N 个）
    """
    path = os.environ.get("CLQ_CANDIDATE_RUNNER")
    if path:
        return load_callable(path)
    return DEFAULT_CANDIDATE_RUNNER


def build_fundamentals_provider() -> Optional[Callable]:
    """
    基本面函数（可选）：CLQ_FUNDA_PROVIDER = "module:get_fundamentals"
    形如 get_fundamentals(code) -> dict，如 {"pe": 15.2, "market_cap": 2.3e10, "sector": "Tech"}
    """
    path = os.environ.get("CLQ_FUNDA_PROVIDER")
    if path:
        return load_callable(path)
    return None


# -----------------------------
# 运行一次选股
# -----------------------------
def run_once(args) -> Dict[str, Any]:
    # 1) TradingAgents Orchestrator & AgentsAdapter
    orchestrator = build_ta_orchestrator(args)
    agents = AgentsAdapter(orchestrator)

    # 2) 准备依赖
    mk_datas = build_market_datas()
    candidate_runner = build_candidate_runner()
    fundamentals = build_fundamentals_provider()

    # 3) 构造 Selector
    frequencys = [args.freq] if args.freq else ["d"]
    selector_cfg = {
        "frequencys": frequencys,
        "max_candidates": int(args.max_candidates or 60),
        "top_k": int(args.top_k or 2),
        "min_score": float(args.min_score or 0.0),
        # 你可在此补充 ma_periods/require_fields/llm_model/enforce_gate/enforce_veto 等
    }
    deps = {
        "market_datas": mk_datas,
        "agents": agents,
        "candidate_runner": candidate_runner,
        "fundamentals": fundamentals,
    }
    selector = build_selector(deps, selector_cfg)

    # 4) 执行选股
    res = selector.select(as_of=args.as_of)
    return res


# -----------------------------
# CLI
# -----------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Run TA_MA_Selector once.")
    p.add_argument("--ta-yaml", type=str, default=os.environ.get("CLQ_TA_YAML"),
                   help="TradingAgents YAML 配置文件路径（留空则从 ENV 读取 CLQ_TA_*）")
    p.add_argument("--as-of", type=str, default=os.environ.get("CLQ_AS_OF"),
                   help="历史回测截止日期（如 2025-10-22），留空则用最新。")
    p.add_argument("--freq", type=str, default=os.environ.get("CLQ_FREQ", "d"),
                   help="主分析周期（默认 d）。")
    p.add_argument("--max-candidates", type=int, default=int(os.environ.get("CLQ_MAX_CANDIDATES", "80")),
                   help="进入多智能体评分的候选数量上限。")
    p.add_argument("--top-k", type=int, default=int(os.environ.get("CLQ_TOP_K", "2")),
                   help="最终锁定标的数量。")
    p.add_argument("--min-score", type=float, default=float(os.environ.get("CLQ_MIN_SCORE", "0.0")),
                   help="模型评分的最低分过滤阈值。")
    p.add_argument("--save-csv", action="store_true", default=os.environ.get("CLQ_SAVE_CSV", "0") == "1",
                   help="保存结果为 CSV 到 ./outputs/ 目录。")
    return p.parse_args()


def main():
    args = parse_args()
    logger.info("Args: %s", vars(args))

    try:
        res = run_once(args)
    except Exception as e:
        logger.exception("Run failed: %s", e)
        raise SystemExit(2)

    symbols = res.get("symbols", [])
    meta = res.get("meta", {})
    df = res.get("data")

    print("\n=== TA_MA_Selector RESULT ===")
    print("Top picks:", symbols)
    print("Meta     :", json.dumps(meta, ensure_ascii=False))

    if isinstance(df, pd.DataFrame) and not df.empty:
        print("\n--- Trade Table ---")
        # 按分数降序预览前 20
        preview = df.sort_values("score", ascending=False).head(20)
        # 避免过宽输出
        with pd.option_context("display.max_columns", 20, "display.width", 160):
            print(preview.to_string(index=False))

        if args.save_csv:
            outdir = Path("outputs")
            outdir.mkdir(parents=True, exist_ok=True)
            asof = args.as_of or "latest"
            outfile = outdir / f"ta_selector_{asof}.csv"
            preview.to_csv(outfile, index=False, encoding="utf-8-sig")
            print(f"\nSaved CSV: {outfile.resolve()}")

    print("\nDone.")


if __name__ == "__main__":
    main()
