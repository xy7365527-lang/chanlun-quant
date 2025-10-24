from __future__ import annotations

import json
import logging
import os
import sys
from collections import OrderedDict
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# Ensure chanlun package is importable
try:
    from chanlun.xuangu import xuangu as xg  # type: ignore
except Exception as exc:  # pragma: no cover
    raise ImportError(
        "无法导入 chanlun.xuangu 模块，请确认 chanlun 项目已在 PYTHONPATH 中。"
    ) from exc

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / 'src'
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Rule registry
# -----------------------------------------------------------------------------

RuleFunc = Callable[[str, Any, Sequence[str]], Optional[Dict[str, Any]]]

RULE_REGISTRY: Dict[str, RuleFunc] = {
    "xg_single_xd_and_bi_mmd": xg.xg_single_xd_and_bi_mmd,
    "xg_multiple_xd_bi_mmd": xg.xg_multiple_xd_bi_mmd,
    "xg_single_xd_bi_zs_zf_5": xg.xg_single_xd_bi_zs_zf_5,
    "xg_single_xd_bi_23_overlapped": xg.xg_single_xd_bi_23_overlapped,
    "xg_single_day_bc_and_up_jincha": xg.xg_single_day_bc_and_up_jincha,
}

DEFAULT_RULES: Tuple[str, ...] = (
    "xg_single_xd_and_bi_mmd",
    "xg_multiple_xd_bi_mmd",
    "xg_single_day_bc_and_up_jincha",
)


def _parse_rules(rule_names: Optional[Iterable[str]]) -> List[RuleFunc]:
    if rule_names is None:
        env_val = os.environ.get("CLQ_CANDIDATE_RULES")
        if env_val:
            try:
                if env_val.strip().startswith("["):
                    rule_names = json.loads(env_val)
                else:
                    rule_names = [r.strip() for r in env_val.split(",") if r.strip()]
            except Exception:
                logger.warning("解析 CLQ_CANDIDATE_RULES 失败，使用默认规则。")
                rule_names = DEFAULT_RULES
        else:
            rule_names = DEFAULT_RULES

    funcs: List[RuleFunc] = []
    for name in rule_names:
        func = RULE_REGISTRY.get(name)
        if func is None:
            logger.warning("候选筛选规则 %s 未注册，忽略。", name)
            continue
        funcs.append(func)
    if not funcs:
        raise ValueError("没有可用的候选筛选规则，请检查配置。")
    return funcs


def _parse_opt_types(opt_type: Optional[Iterable[str]]) -> List[str]:
    if opt_type is None:
        env_val = os.environ.get("CLQ_CANDIDATE_OPT")
        if env_val:
            opt_type = [item.strip() for item in env_val.split(",") if item.strip()]
    return list(opt_type or ["long"])


def _ensure_cl_ready(
    mk_datas: Any, code: str, frequencys: Sequence[str], as_of: Optional[str]
) -> None:
    """
    预先加载缠论数据，避免后续规则函数重复处理。
    """
    for freq in frequencys:
        try:
            mk_datas.get_cl_data(code, freq, end_date=as_of, cl_config=getattr(mk_datas, "cl_config", {}))
        except TypeError:
            mk_datas.get_cl_data(code, freq, end_date=as_of)
        except Exception as exc:
            logger.debug("获取 %s@%s 缠论数据失败: %s", code, freq, exc)


def merge_candidates(
    mk_datas: Any,
    frequencys: Sequence[str],
    as_of: Optional[str] = None,
    rule_names: Optional[Iterable[str]] = None,
    opt_type: Optional[Iterable[str]] = None,
) -> List[str]:
    """
    综合一买/二买/三买/背驰等策略生成候选股票列表。

    Args:
        mk_datas: 市场数据对象，需提供 codes/get_cl_data 等接口。
        frequencys: 分析周期列表，至少包含主频。
        as_of: 回测截止时间，可选。
        rule_names: 筛选规则名称列表；默认读取环境变量或 DEFAULT_RULES。
        opt_type: 多空方向（如 ["long"], ["short"]），默认长多。

    Returns:
        候选股票代码列表（按命中顺序去重）。
    """

    codes: Sequence[str] = getattr(mk_datas, "codes", [])
    if not codes:
        raise ValueError("market_datas.codes 为空，无法构建候选池。")

    rules = _parse_rules(rule_names)
    directions = _parse_opt_types(opt_type)

    logger.info(
        "运行候选筛选：codes=%d, frequencys=%s, rules=%s, opt_type=%s",
        len(codes),
        list(frequencys),
        [func.__name__ for func in rules],
        directions,
    )

    results: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

    for code in codes:
        try:
            _ensure_cl_ready(mk_datas, code, frequencys[:2], as_of)
        except Exception as exc:
            logger.debug("预加载 %s 缠论数据失败: %s", code, exc)

    for func in rules:
        for code in codes:
            try:
                hit = func(code, mk_datas, directions)
            except Exception as exc:
                logger.debug("规则 %s 处理 %s 时出错: %s", func.__name__, code, exc)
                continue
            if not hit:
                continue
            record = results.setdefault(code, {"rules": []})
            record["rules"].append(
                {
                    "rule": func.__name__,
                    "message": hit.get("msg") if isinstance(hit, dict) else "",
                }
            )

    ordered_codes = list(results.keys()) or list(codes)
    logger.info("候选筛选完成，命中 %d 个标的。", len(ordered_codes))
    return ordered_codes


__all__ = ["merge_candidates"]
