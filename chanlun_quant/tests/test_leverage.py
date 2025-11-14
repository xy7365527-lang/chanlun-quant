from chanlun_quant.risk.leverage import (
    LeverageCaps,
    combine_leverage,
    estimate_liq_price,
    safe_leverage_cap_by_stop,
)


class Cfg:
    exch_max_leverage = 50.0
    max_leverage_config = 30.0
    leverage_step = 1.0
    exch_maint_margin = 0.004
    liq_buffer_ratio = 0.2
    risk_per_trade_pct = 0.01
    min_stop_distance_pct = 0.002
    atr_vol_norm = 0.01


def test_safe_leverage_cap_by_stop() -> None:
    caps = LeverageCaps(L_exch_max=50.0, L_cfg_max=30.0, step=1.0, mm=0.004, buffer=0.2)
    lever = safe_leverage_cap_by_stop(100.0, 98.0, "long", caps)
    assert 29.0 <= lever <= 30.0


def test_estimate_liq_price_monotonic() -> None:
    pl = estimate_liq_price(100.0, "long", 10.0, 0.004)
    ph = estimate_liq_price(100.0, "long", 20.0, 0.004)
    assert ph < pl


def test_combine_leverage_reasonable() -> None:
    cfg = Cfg()
    out = combine_leverage(
        entry=100.0,
        stop=99.0,
        side="long",
        remaining_capital=10_000.0,
        equity=20_000.0,
        atr_norm=0.01,
        fusion_score=0.8,
        confidence=0.7,
        cfg=cfg,
    )
    assert 1.0 <= out["L_suggest"] <= cfg.max_leverage_config

