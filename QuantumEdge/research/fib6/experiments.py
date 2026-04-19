"""
fib6 experiment configs.

Phase 1: Vol regime gate variants for xlk_style / qqq_style / spy_style
Phase 2: 1H execution variants (SPY only has real 1H; XLK/QQQ fall back to daily)
Phase 3: Portfolio construction (uses Phase 1 survivors)
Phase 4: OOS + friction for best Phase 1 configs

Portfolio universe (instruments with positive xlk_style in fib5):
  XLK, QQQ, IWM, XLY, XLF
"""

from __future__ import annotations

from research.fib6.model import Fib6Config

# ---------------------------------------------------------------------------
# Instrument sets
# ---------------------------------------------------------------------------

PHASE1_VOL_TICKERS = ["XLK", "QQQ", "SPY", "IWM", "XLY", "XLV", "XLF", "XLE"]
PHASE2_1H_TICKERS = ["SPY"]  # Only SPY has hourly data
PHASE2_DAILY_TICKERS = ["XLK", "QQQ"]  # Daily-only; 1H triggers will fall back
PORTFOLIO_UNIVERSE = ["XLK", "QQQ", "IWM", "XLY", "XLF"]
OOS_TICKERS = ["XLK", "QQQ", "SPY", "IWM", "XLY"]

SLIPPAGE_REALISTIC = 0.0005
SLIPPAGE_CONSERVATIVE = 0.001

# ---------------------------------------------------------------------------
# Base style factories
# ---------------------------------------------------------------------------


def _base_xlk(vol_gate: str = "neutral", slippage: float = 0.0) -> Fib6Config:
    cfg = Fib6Config()
    cfg.name = f"xlk_{vol_gate}" if vol_gate != "neutral" else "xlk_neutral"
    cfg.quality_min_score = 0.0
    cfg.quality_min_sweep = 15.0
    cfg.require_sweep = True
    cfg.min_displacement_atr = 2.0
    cfg.entry_trigger = "touch_rejection"
    cfg.stop_variant = "origin"
    cfg.target_fib = 1.618
    cfg.slippage_pct = slippage
    cfg.vol_regime_gate = vol_gate
    return cfg


def _base_qqq(vol_gate: str = "neutral", slippage: float = 0.0) -> Fib6Config:
    cfg = Fib6Config()
    cfg.name = f"qqq_{vol_gate}" if vol_gate != "neutral" else "qqq_neutral"
    cfg.quality_min_score = 60.0
    cfg.require_sweep = True
    cfg.min_displacement_atr = 2.0
    cfg.entry_trigger = "midzone_only"
    cfg.midzone_tolerance_atr = 0.20
    cfg.stop_variant = "origin"
    cfg.target_fib = 1.618
    cfg.slippage_pct = slippage
    cfg.vol_regime_gate = vol_gate
    return cfg


def _base_spy(vol_gate: str = "neutral", slippage: float = 0.0) -> Fib6Config:
    cfg = Fib6Config()
    cfg.name = f"spy_{vol_gate}" if vol_gate != "neutral" else "spy_neutral"
    cfg.quality_min_score = 75.0
    cfg.require_sweep = True
    cfg.min_displacement_atr = 2.0
    cfg.entry_trigger = "nextbar_confirm"
    cfg.nextbar_confirm_atr = 0.30
    cfg.stop_variant = "origin"
    cfg.target_fib = 1.618
    cfg.slippage_pct = slippage
    cfg.vol_regime_gate = vol_gate
    return cfg


# ---------------------------------------------------------------------------
# Phase 1: Vol gate variants
# ---------------------------------------------------------------------------


def get_phase1_configs() -> dict[str, Fib6Config]:
    """9 vol gate configs: 3 strategies x 3 gate modes."""
    return {
        "xlk_neutral": _base_xlk("neutral"),
        "xlk_vol_quiet": _base_xlk("vol_quiet"),
        "xlk_vol_active": _base_xlk("vol_active"),
        "qqq_neutral": _base_qqq("neutral"),
        "qqq_vol_active": _base_qqq("vol_active"),
        "qqq_vol_quiet": _base_qqq("vol_quiet"),
        "spy_neutral": _base_spy("neutral"),
        "spy_vol_active": _base_spy("vol_active"),
        "spy_vol_quiet": _base_spy("vol_quiet"),
    }


# ---------------------------------------------------------------------------
# Phase 2: 1H execution variants
# ---------------------------------------------------------------------------


def get_phase2_configs_1h() -> dict[str, Fib6Config]:
    """
    1H execution variants for SPY (real hourly data available).
    Baseline: touch_rejection on daily. Compare against all 1H triggers.
    """

    def _spy_trig(trigger: str, name: str) -> Fib6Config:
        cfg = _base_spy("neutral")
        cfg.name = name
        cfg.entry_trigger = trigger
        cfg.quality_min_score = 60.0  # Broaden for sample size
        return cfg

    return {
        "spy_daily_baseline": _spy_trig("touch_rejection", "spy_daily_base"),
        "spy_1h_rejection": _spy_trig("1h_rejection", "spy_1h_reject"),
        "spy_1h_structure_shift": _spy_trig("1h_structure_shift", "spy_1h_struct"),
        "spy_1h_displacement_off": _spy_trig("1h_displacement_off", "spy_1h_disp"),
        "spy_1h_reclaim_sweep": _spy_trig("1h_reclaim_after_sweep", "spy_1h_reclaim"),
    }


def get_phase2_configs_daily() -> dict[str, Fib6Config]:
    """
    Daily execution variants for XLK and QQQ (no hourly data).
    Tests whether different daily triggers outperform the fib5 winner.
    """

    def _xlk_trig(trigger: str, name: str) -> Fib6Config:
        cfg = _base_xlk("vol_quiet")
        cfg.name = name
        cfg.entry_trigger = trigger
        return cfg

    def _qqq_trig(trigger: str, name: str) -> Fib6Config:
        cfg = _base_qqq("vol_active")
        cfg.name = name
        cfg.entry_trigger = trigger
        return cfg

    return {
        "xlk_touch_rejection": _xlk_trig("touch_rejection", "xlk_vq_touch"),
        "xlk_close_in_zone": _xlk_trig("close_in_zone", "xlk_vq_ciz"),
        "xlk_nextbar_confirm": _xlk_trig("nextbar_confirm", "xlk_vq_nbc"),
        "xlk_midzone_only": _xlk_trig("midzone_only", "xlk_vq_mid"),
        "xlk_displacement_off": _xlk_trig("displacement_off", "xlk_vq_disp"),
        "qqq_midzone_only": _qqq_trig("midzone_only", "qqq_va_mid"),
        "qqq_touch_rejection": _qqq_trig("touch_rejection", "qqq_va_touch"),
        "qqq_close_in_zone": _qqq_trig("close_in_zone", "qqq_va_ciz"),
        "qqq_nextbar_confirm": _qqq_trig("nextbar_confirm", "qqq_va_nbc"),
        "qqq_displacement_off": _qqq_trig("displacement_off", "qqq_va_disp"),
    }


# ---------------------------------------------------------------------------
# Phase 3: Portfolio construction uses Phase 1 survivors
# (configs are determined at runtime after Phase 1 completes)
# ---------------------------------------------------------------------------


def make_portfolio_config(
    base_style: str = "xlk",
    vol_gate: str = "vol_quiet",
    slippage: float = SLIPPAGE_REALISTIC,
) -> Fib6Config:
    """Return a friction-adjusted portfolio config for one instrument."""
    if base_style == "xlk":
        cfg = _base_xlk(vol_gate, slippage)
    elif base_style == "qqq":
        cfg = _base_qqq(vol_gate, slippage)
    else:
        cfg = _base_spy(vol_gate, slippage)
    cfg.name = f"port_{base_style}_{vol_gate}"
    return cfg


# ---------------------------------------------------------------------------
# Phase 4: Best configs with friction
# ---------------------------------------------------------------------------


def get_phase4_configs() -> dict[str, Fib6Config]:
    """Best configs from Phase 1 with realistic friction applied."""
    return {
        "xlk_vol_quiet_5bps": _base_xlk("vol_quiet", SLIPPAGE_REALISTIC),
        "xlk_vol_quiet_10bps": _base_xlk("vol_quiet", SLIPPAGE_CONSERVATIVE),
        "qqq_vol_active_5bps": _base_qqq("vol_active", SLIPPAGE_REALISTIC),
        "qqq_vol_active_10bps": _base_qqq("vol_active", SLIPPAGE_CONSERVATIVE),
        "xlk_neutral_5bps": _base_xlk("neutral", SLIPPAGE_REALISTIC),
        "qqq_neutral_5bps": _base_qqq("neutral", SLIPPAGE_REALISTIC),
    }


# ---------------------------------------------------------------------------
# Grid helper factories (used by robustness.py)
# ---------------------------------------------------------------------------


def _make_xlk_quiet_grid_cfg(
    sweep_min: float,
    disp_atr: float,
    stop: str,
    target: float,
) -> Fib6Config:
    cfg = Fib6Config()
    cfg.quality_min_sweep = sweep_min
    cfg.quality_min_score = 0.0
    cfg.require_sweep = True
    cfg.min_displacement_atr = disp_atr
    cfg.entry_trigger = "touch_rejection"
    cfg.stop_variant = stop
    cfg.target_fib = target
    cfg.vol_regime_gate = "vol_quiet"
    cfg.name = f"xlk_vq_g_sw{sweep_min:.0f}_d{disp_atr:.1f}_st{stop[:3]}_tgt{target:.3f}"
    return cfg


def _make_qqq_active_grid_cfg(
    q_min: float,
    tol: float,
    stop: str,
    target: float,
) -> Fib6Config:
    cfg = Fib6Config()
    cfg.quality_min_score = q_min
    cfg.require_sweep = True
    cfg.min_displacement_atr = 2.0
    cfg.entry_trigger = "midzone_only"
    cfg.midzone_tolerance_atr = tol
    cfg.stop_variant = stop
    cfg.target_fib = target
    cfg.vol_regime_gate = "vol_active"
    cfg.name = f"qqq_va_g_q{q_min:.0f}_tol{tol:.2f}_st{stop[:3]}_tgt{target:.3f}"
    return cfg
