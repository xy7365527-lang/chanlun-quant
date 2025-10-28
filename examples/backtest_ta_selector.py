# -*- coding: utf-8 -*-
"""
Backtest TA_MA_Selector by iterating over trading days.
This script reuses the wiring helpers from `wire_ta_selector.py`.

Example:
    python examples/backtest_ta_selector.py \
        --start 2024-01-02 \
        --end 2024-12-31 \
        --hold-days 5 \
        --freq d
"""
from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from examples.wire_ta_selector import (
    build_candidate_runner,
    build_fundamentals_provider,
    build_market_datas,
    build_ta_orchestrator,
    parse_args as parse_wire_args,
)
from chanlun_quant.agents.adapter import AgentsAdapter
from chanlun_quant.selectors.llm_ma_selector import build as build_selector


def _list_trading_days(df: pd.DataFrame, start: str, end: str) -> List[str]:
    date_col: Optional[str] = None
    for col in ("date", "datetime", "time"):
        if col in df.columns:
            date_col = col
            break
    if date_col is None:
        raise ValueError("K-line dataframe must include date/datetime column.")
    series = pd.to_datetime(df[date_col])
    mask = (series >= pd.Timestamp(start)) & (series <= pd.Timestamp(end))
    days = sorted(series[mask].dt.normalize().unique())
    return [pd.Timestamp(d).strftime("%Y-%m-%d") for d in days]


def _next_open_price(mk_datas: Any, code: str, trade_date: str) -> float:
    df = mk_datas.get_kline_df(code, "d")
    if df is None or df.empty:
        return math.nan
    df = df[df["date"] > pd.Timestamp(trade_date)].head(1)
    return float(df["open"].iloc[0]) if len(df) > 0 else math.nan


def _close_price(mk_datas: Any, code: str, trade_date: str) -> float:
    df = mk_datas.get_kline_df(code, "d")
    if df is None or df.empty:
        return math.nan
    df = df[df["date"] == pd.Timestamp(trade_date)]
    return float(df["close"].iloc[0]) if len(df) > 0 else math.nan


@dataclass
class Position:
    symbol: str
    entry_date: str
    entry_price: float
    deadline: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest TA_MA_Selector.")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD backtest start date.")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD backtest end date.")
    parser.add_argument("--hold-days", type=int, default=5, help="Holding period in trading days.")
    parser.add_argument(
        "--freq", type=str, default=os.environ.get("CLQ_FREQ", "d"), help="Primary analysis frequency."
    )
    parser.add_argument(
        "--max-candidates", type=int, default=int(os.environ.get("CLQ_MAX_CANDIDATES", "80"))
    )
    parser.add_argument("--top-k", type=int, default=int(os.environ.get("CLQ_TOP_K", "2")))
    parser.add_argument("--min-score", type=float, default=float(os.environ.get("CLQ_MIN_SCORE", "0.0")))
    parser.add_argument("--outdir", default="outputs/backtest", help="Directory to store results.")
    return parser.parse_args()


def _build_selector(args: argparse.Namespace):
    wire_args = argparse.Namespace(
        ta_yaml=os.environ.get("CLQ_TA_YAML"),
        as_of=None,
        freq=args.freq,
        max_candidates=args.max_candidates,
        top_k=args.top_k,
        min_score=args.min_score,
        save_csv=False,
    )
    orchestrator = build_ta_orchestrator(wire_args)
    agents = AgentsAdapter(orchestrator)
    mk_datas = build_market_datas()
    candidate_runner = build_candidate_runner()
    fundamentals = build_fundamentals_provider()

    deps = {
        "market_datas": mk_datas,
        "agents": agents,
        "candidate_runner": candidate_runner,
        "fundamentals": fundamentals,
    }
    selector = build_selector(
        deps,
        {
            "frequencys": [args.freq],
            "max_candidates": args.max_candidates,
            "top_k": args.top_k,
            "min_score": args.min_score,
        },
    )
    return selector, mk_datas


def main() -> None:
    args = parse_args()
    Path(args.outdir).mkdir(parents=True, exist_ok=True)
    selector, mk_datas = _build_selector(args)

    codes = getattr(mk_datas, "codes", [])
    if not codes:
        raise SystemExit("market_datas.codes is empty; cannot run backtest.")

    # Derive trading calendar from the first symbol's daily data.
    day_df = mk_datas.get_kline_df(codes[0], "d")
    trading_days = _list_trading_days(day_df, args.start, args.end)

    positions: Dict[str, Position] = {}
    trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []
    equity = 1.0
    peak = 1.0

    for trade_date in trading_days:
        result = selector.select(as_of=trade_date)
        picks = result.get("symbols", []) or []

        # Enter positions at next day's open.
        for symbol in picks:
            if symbol in positions:
                continue
            entry_price = _next_open_price(mk_datas, symbol, trade_date)
            if math.isnan(entry_price):
                continue
            deadline = (pd.Timestamp(trade_date) + pd.Timedelta(days=args.hold_days)).strftime("%Y-%m-%d")
            positions[symbol] = Position(symbol=symbol, entry_date=trade_date, entry_price=entry_price, deadline=deadline)

        # Exit rules.
        exits = []
        for symbol, pos in positions.items():
            if trade_date >= pos.deadline:
                exits.append(symbol)
                continue
            close_px = _close_price(mk_datas, symbol, trade_date)
            if math.isnan(close_px):
                continue
            if (close_px / pos.entry_price) - 1 <= -0.05:
                exits.append(symbol)

        for symbol in exits:
            close_px = _close_price(mk_datas, symbol, trade_date)
            if math.isnan(close_px):
                continue
            pos = positions.pop(symbol)
            ret = (close_px / pos.entry_price) - 1
            trades.append(
                {
                    "symbol": symbol,
                    "entry_date": pos.entry_date,
                    "entry_price": pos.entry_price,
                    "exit_date": trade_date,
                    "exit_price": close_px,
                    "return": ret,
                }
            )

        # Mark-to-market equity (simple average of open positions; adjust to your sizing rules).
        if positions:
            mtm_returns = []
            for symbol, pos in positions.items():
                close_px = _close_price(mk_datas, symbol, trade_date)
                if math.isnan(close_px):
                    continue
                mtm_returns.append((close_px / pos.entry_price) - 1)
            day_ret = sum(mtm_returns) / len(mtm_returns) if mtm_returns else 0.0
            # This scaling is illustrative; adjust to your capital allocation.
            equity *= 1 + (day_ret / 10.0)
        peak = max(peak, equity)
        equity_curve.append({"date": trade_date, "equity": equity, "drawdown": equity / peak - 1})

    trades_df = pd.DataFrame(trades)
    curve_df = pd.DataFrame(equity_curve)
    out_prefix = Path(args.outdir) / f"ta_selector_bt_{args.start}_{args.end}"
    trades_df.to_csv(f"{out_prefix}_trades.csv", index=False)
    curve_df.to_csv(f"{out_prefix}_equity.csv", index=False)

    win_rate = (trades_df["return"] > 0).mean() if not trades_df.empty else 0.0
    avg_ret = trades_df["return"].mean() if not trades_df.empty else 0.0
    max_dd = curve_df["drawdown"].min() if not curve_df.empty else 0.0

    print("\n=== BACKTEST SUMMARY ===")
    print(f"Trades: {len(trades_df)} | WinRate: {win_rate:.2%} | AvgRet/Trade: {avg_ret:.2%} | MaxDD: {max_dd:.2%}")
    print(f"Outputs: {out_prefix}_trades.csv, {out_prefix}_equity.csv")


if __name__ == "__main__":
    main()
