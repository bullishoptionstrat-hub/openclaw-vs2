"""
fib5 experiment strategy configs.

These are ticker-agnostic strategy configs applied across the replication set.
Each strategy maps to a Fib5Config that can be applied to any available ticker.

Naming:
  xlk_style    — sweep_deep + touch_rejection (proven on XLK in fib4)
  qqq_style    — midzone_only Q>=60 (proven on QQQ in fib4)
  spy_style    — nextbar_confirm, tier A (thin-sample SPY result)
  baseline_ciz — close_in_zone, Q>=60 (fib3 equivalent baseline)

Replication instrument sets:
  TECH_GROWTH  — XLK, QQQ, XLY (sector ETFs expected to behave like XLK/QQQ)
  DEFENSIVE    — XLV, XLU, XLP, XLRE
  CYCLICAL     — XLF, XLE, XLI, XLB, XLC
  BROAD        — SPY, IWM
"""

from __future__ import annotations

from research.fib5.model import Fib5Config

# ---------------------------------------------------------------------------
# Replication sets
# ---------------------------------------------------------------------------

TECH_GROWTH = ["XLK", "QQQ", "XLY"]
DEFENSIVE = ["XLV", "XLU", "XLP", "XLRE"]
CYCLICAL = ["XLF", "XLE", "XLI", "XLB", "XLC"]
BROAD = ["SPY", "IWM"]

ALL_REPLICATION_TICKERS = TECH_GROWTH + DEFENSIVE + CYCLICAL + BROAD

# Focused set for OOS and robustness (compute-heavy)
OOS_TICKERS = ["XLK", "QQQ", "SPY", "IWM", "XLV", "XLY"]

# ---------------------------------------------------------------------------
# Strategy configs
# ---------------------------------------------------------------------------


def make_xlk_style(
    slippage_pct: float = 0.0,
    stop_variant: str = "origin",
    target_fib: float = 1.618,
) -> Fib5Config:
    """XLK-style: sweep_deep (>=15) + touch_rejection."""
    cfg = Fib5Config()
    cfg.name = "xlk_style"
    cfg.quality_min_score = 0.0
    cfg.quality_min_sweep = 15.0
    cfg.require_sweep = True
    cfg.min_displacement_atr = 2.0
    cfg.entry_trigger = "touch_rejection"
    cfg.stop_variant = stop_variant
    cfg.target_fib = target_fib
    cfg.slippage_pct = slippage_pct
    return cfg


def make_qqq_style(
    slippage_pct: float = 0.0,
    stop_variant: str = "origin",
    target_fib: float = 1.618,
) -> Fib5Config:
    """QQQ-style: midzone_only, Q>=60."""
    cfg = Fib5Config()
    cfg.name = "qqq_style"
    cfg.quality_min_score = 60.0
    cfg.require_sweep = True
    cfg.min_displacement_atr = 2.0
    cfg.entry_trigger = "midzone_only"
    cfg.midzone_tolerance_atr = 0.20
    cfg.stop_variant = stop_variant
    cfg.target_fib = target_fib
    cfg.slippage_pct = slippage_pct
    return cfg


def make_spy_style(slippage_pct: float = 0.0) -> Fib5Config:
    """SPY-style: nextbar_confirm, tier A (thin sample in fib4)."""
    cfg = Fib5Config()
    cfg.name = "spy_style"
    cfg.quality_min_score = 75.0
    cfg.require_sweep = True
    cfg.min_displacement_atr = 2.0
    cfg.entry_trigger = "nextbar_confirm"
    cfg.nextbar_confirm_atr = 0.30
    cfg.stop_variant = "origin"
    cfg.target_fib = 1.618
    cfg.slippage_pct = slippage_pct
    return cfg


def make_baseline(slippage_pct: float = 0.0) -> Fib5Config:
    """Baseline: close_in_zone, Q>=60 — fib3 equivalent."""
    cfg = Fib5Config()
    cfg.name = "baseline_ciz"
    cfg.quality_min_score = 60.0
    cfg.require_sweep = True
    cfg.min_displacement_atr = 2.0
    cfg.entry_trigger = "close_in_zone"
    cfg.stop_variant = "origin"
    cfg.target_fib = 1.618
    cfg.slippage_pct = slippage_pct
    return cfg


# ---------------------------------------------------------------------------
# Friction variants
# ---------------------------------------------------------------------------

SLIPPAGE_REALISTIC = 0.0005  # 5bps per leg
SLIPPAGE_CONSERVATIVE = 0.001  # 10bps per leg


def get_strategies(with_friction: bool = False) -> dict[str, Fib5Config]:
    """
    Return the core strategy configs.
    If with_friction=True, uses realistic (5bps) slippage.
    """
    slip = SLIPPAGE_REALISTIC if with_friction else 0.0
    return {
        "xlk_style": make_xlk_style(slippage_pct=slip),
        "qqq_style": make_qqq_style(slippage_pct=slip),
        "spy_style": make_spy_style(slippage_pct=slip),
        "baseline_ciz": make_baseline(slippage_pct=slip),
    }
