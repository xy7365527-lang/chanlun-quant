from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from chanlun_quant.ai.interface import ChanLLM
from chanlun_quant.broker.interface import BrokerInterface
from chanlun_quant.config import Config
from chanlun_quant.core.fractal import detect_on_normalized
from chanlun_quant.core.fugue import fuse_levels
from chanlun_quant.core.kline import normalize
from chanlun_quant.core.momentum import compute_macd
from chanlun_quant.core.pivot import detect_centrals
from chanlun_quant.core.segment import build_segments
from chanlun_quant.core.signal import detect_signals
from chanlun_quant.core.stroke import build_strokes
from chanlun_quant.types import (
    Bar,
    Central,
    PositionState,
    Segment,
    Signal,
    StructureState,
)

try:
    from chanlun_quant.strategy.trade_rhythm import TradeRhythmEngine
except Exception:  # pragma: no cover - optional dependency
    TradeRhythmEngine = None  # type: ignore[assignment]


class ChanlunEngine:
    """Orchestrates Chanlun multi-level analysis, AI decisioning, and execution."""

    def __init__(
        self,
        cfg: Config,
        llm: Optional[ChanLLM] = None,
        broker: Optional[BrokerInterface] = None,
    ) -> None:
        self.cfg = cfg
        self.llm = llm or ChanLLM()
        self.broker = broker
        self.rhythm = TradeRhythmEngine() if TradeRhythmEngine is not None else None

    # ------------------------------------------------------------------ #
    # Single level pipeline
    # ------------------------------------------------------------------ #
    def analyze_one_level(self, bars: List[Bar], level: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {"level": level}
        if not bars:
            result.update(
                {
                    "bars": [],
                    "fractals": [],
                    "strokes": [],
                    "segments": [],
                    "centrals": [],
                    "macd": {},
                    "signals": [],
                }
            )
            return result

        normalized = normalize(bars)
        fractals = detect_on_normalized(normalized)
        strokes = build_strokes(
            fractals,
            normalized,
            min_bars_per_pen=self.cfg.min_bars_per_pen,
        )
        segments = build_segments(
            strokes,
            strict_feature_sequence=self.cfg.strict_feature_sequence,
            gap_tolerance=self.cfg.gap_tolerance,
        )
        centrals = detect_centrals(strokes, overlap_ratio=self.cfg.central_overlap_ratio)
        macd = compute_macd([bar.close for bar in normalized])
        signals = detect_signals(
            segments,
            centrals,
            macd,
            cfg=self.cfg,
        )

        result.update(
            {
                "bars": normalized,
                "fractals": fractals,
                "strokes": strokes,
                "segments": segments,
                "centrals": centrals,
                "macd": macd,
                "signals": signals,
            }
        )
        return result

    # ------------------------------------------------------------------ #
    # Multi-level aggregation
    # ------------------------------------------------------------------ #
    def analyze_multi_level(self, level_bars: Dict[str, List[Bar]]) -> Dict[str, Any]:
        levels_out: Dict[str, Dict[str, Any]] = {}
        signals_by_level: Dict[str, List[Signal]] = {}

        structure = StructureState()
        structure.levels = list(level_bars.keys())

        for level, bars in level_bars.items():
            analysis = self.analyze_one_level(bars, level)
            levels_out[level] = analysis
            signals_by_level[level] = analysis.get("signals", [])

        structure.signals = signals_by_level
        structure.centrals = {
            level: levels_out[level].get("centrals", []) for level in levels_out
        }
        structure.trends = {}  # TODO: derive from segments/strokes when available

        fusion = fuse_levels(signals_by_level)
        structure.relations = fusion

        return {"levels": levels_out, "structure": structure, "fusion": fusion}

    # ------------------------------------------------------------------ #
    # Decision & execution loop
    # ------------------------------------------------------------------ #
    def decide_and_execute(
        self,
        level_bars: Dict[str, List[Bar]],
        position_state: PositionState,
    ) -> Dict[str, Any]:
        analysis = self.analyze_multi_level(level_bars)
        structure = analysis["structure"]

        if self.rhythm is not None:
            try:
                position_state.stage = self.rhythm.update(structure, position_state)
            except Exception:  # pragma: no cover - defensive fallback
                pass

        ai_out = self.llm.decide_action(structure, position_state, self.cfg)
        instruction = ai_out.get("instruction", {"action": "HOLD", "quantity": 0})

        execution: Dict[str, Any] = {"status": "skipped", "order": None}
        action = instruction.get("action")
        quantity = int(instruction.get("quantity", 0) or 0)

        if (
            action in {"BUY", "SELL"}
            and quantity > 0
            and self.broker is not None
        ):
            last_price = self._latest_price(level_bars)
            order = self.broker.place_order(action, quantity, self.cfg.symbol, price=last_price)
            execution = {"status": "filled", "order": order}
            self._apply_execution(position_state, action, quantity, last_price)

        return {
            "analysis": analysis,
            "ai": ai_out,
            "execution": execution,
            "position": asdict(position_state),
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _latest_price(self, level_bars: Dict[str, List[Bar]]) -> Optional[float]:
        for bars in level_bars.values():
            if bars:
                return bars[-1].close
        return None

    def _apply_execution(
        self,
        position_state: PositionState,
        action: str,
        quantity: int,
        price: Optional[float],
    ) -> None:
        if price is None or quantity <= 0:
            return

        if action == "BUY":
            old_qty = position_state.quantity
            new_qty = old_qty + quantity
            if new_qty > 0:
                if old_qty > 0:
                    position_state.avg_cost = (
                        position_state.avg_cost * old_qty + price * quantity
                    ) / new_qty
                else:
                    position_state.avg_cost = price
            position_state.quantity = new_qty
        elif action == "SELL":
            sell_qty = min(quantity, position_state.quantity)
            position_state.realized_profit += (price - position_state.avg_cost) * sell_qty
            position_state.quantity -= sell_qty
            if position_state.quantity <= 0:
                position_state.quantity = 0
                position_state.avg_cost = 0.0
