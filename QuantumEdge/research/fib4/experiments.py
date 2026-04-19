"""
fib4 experiment configurations.

Organized by instrument family:
  spy_*   — SPY experiments (1H data available)
  xlk_*   — XLK experiments (daily only, sweep-quality focus)
  qqq_*   — QQQ experiments (daily only, 1H falls back)

Naming convention:
  {ticker}_{quality_filter}_{trigger}

Each experiment dict overrides Fib4Config defaults.
quality_min_score=75 -> Tier A only
quality_min_score=60 -> Tier B+ (A+B)
quality_min_sweep=15 -> sweep-deep filter
"""

from __future__ import annotations

from research.fib4.model import Fib4Config

FIB4_EXPERIMENTS: dict[str, dict] = {
    # =========================================================================
    # SPY — 1H data available; all triggers valid
    # =========================================================================
    # ── Baseline: fib3-equivalent daily close-in-zone ────────────────────────
    "spy_tierA_baseline": {
        "name": "spy_tierA_baseline",
        "quality_min_score": 75.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    # ── Primary execution experiments (mandatory) ────────────────────────────
    "spy_tierA_touch_rejection": {
        "name": "spy_tierA_touch_rejection",
        "quality_min_score": 75.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "touch_rejection",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "spy_tierA_nextbar_confirm": {
        "name": "spy_tierA_nextbar_confirm",
        "quality_min_score": 75.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "nextbar_confirm",
        "nextbar_confirm_atr": 0.30,
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "spy_tierA_1h_confirm": {
        # 1H rejection trigger; SPY has hourly data
        "name": "spy_tierA_1h_confirm",
        "quality_min_score": 75.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "1h_rejection",
        "fallback_trigger": "touch_rejection",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "spy_midzone_only": {
        # Tier B+ (A+B), entries only near the 0.5 midpoint
        "name": "spy_midzone_only",
        "quality_min_score": 60.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "midzone_only",
        "midzone_tolerance_atr": 0.20,
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    # ── Additional SPY variants ───────────────────────────────────────────────
    "spy_tierA_1h_structure": {
        "name": "spy_tierA_1h_structure",
        "quality_min_score": 75.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "1h_structure_shift",
        "fallback_trigger": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "spy_choch_touch_rejection": {
        # CHoCH-decisive legs (choch_score >= 15) with touch_rejection
        "name": "spy_choch_touch_rejection",
        "quality_min_score": 0.0,
        "quality_min_choch": 15.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "touch_rejection",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "spy_tierA_zone0382": {
        # Entry near 0.382 level (fib_382, deep retracement zone bottom)
        "name": "spy_tierA_zone0382",
        "quality_min_score": 75.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "zone_0382_only",
        "midzone_tolerance_atr": 0.20,
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "spy_tierA_zone0618": {
        # Entry near 0.618 level (fib_618, shallow retracement zone top)
        "name": "spy_tierA_zone0618",
        "quality_min_score": 75.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "zone_0618_only",
        "midzone_tolerance_atr": 0.20,
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "spy_tierA_no_passive": {
        # Touch rejection with passive drift filter (max 3 passive bars)
        "name": "spy_tierA_no_passive",
        "quality_min_score": 75.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "touch_rejection",
        "no_passive_max_bars": 3,
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    # =========================================================================
    # XLK — daily only; sweep quality drives the edge (not total score)
    # =========================================================================
    "xlk_sweep_deep_baseline": {
        "name": "xlk_sweep_deep_baseline",
        "quality_min_score": 0.0,
        "quality_min_sweep": 15.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "xlk_sweep_deep_rejection": {
        # mandatory
        "name": "xlk_sweep_deep_rejection",
        "quality_min_score": 0.0,
        "quality_min_sweep": 15.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "touch_rejection",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "xlk_sweep_deep_nextbar": {
        "name": "xlk_sweep_deep_nextbar",
        "quality_min_score": 0.0,
        "quality_min_sweep": 15.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "nextbar_confirm",
        "nextbar_confirm_atr": 0.30,
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "xlk_sweep_deep_1h_confirm": {
        # mandatory (falls back to close_in_zone since XLK has no hourly data)
        "name": "xlk_sweep_deep_1h_confirm",
        "quality_min_score": 0.0,
        "quality_min_sweep": 15.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "1h_rejection",
        "fallback_trigger": "touch_rejection",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "xlk_tierB_rejection": {
        "name": "xlk_tierB_rejection",
        "quality_min_score": 60.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "touch_rejection",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "xlk_midzone_only": {
        "name": "xlk_midzone_only",
        "quality_min_score": 0.0,
        "quality_min_sweep": 15.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "midzone_only",
        "midzone_tolerance_atr": 0.20,
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    # =========================================================================
    # QQQ — daily only; 1H falls back to daily
    # =========================================================================
    "qqq_tierA_baseline": {
        "name": "qqq_tierA_baseline",
        "quality_min_score": 75.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "qqq_tierA_touch_rejection": {
        "name": "qqq_tierA_touch_rejection",
        "quality_min_score": 75.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "touch_rejection",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "qqq_tierA_1h_confirm": {
        # mandatory (falls back to touch_rejection since QQQ is daily-only)
        "name": "qqq_tierA_1h_confirm",
        "quality_min_score": 75.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "1h_rejection",
        "fallback_trigger": "touch_rejection",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "qqq_midzone_only": {
        # mandatory
        "name": "qqq_midzone_only",
        "quality_min_score": 60.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "midzone_only",
        "midzone_tolerance_atr": 0.20,
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "qqq_sweep_deep_rejection": {
        "name": "qqq_sweep_deep_rejection",
        "quality_min_score": 0.0,
        "quality_min_sweep": 15.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_trigger": "touch_rejection",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
}

# Mandatory first experiment set (as specified)
MANDATORY_EXPERIMENTS = [
    ("spy_tierA_touch_rejection", "SPY"),
    ("spy_tierA_nextbar_confirm", "SPY"),
    ("spy_tierA_1h_confirm", "SPY"),
    ("spy_midzone_only", "SPY"),
    ("xlk_sweep_deep_rejection", "XLK"),
    ("xlk_sweep_deep_1h_confirm", "XLK"),
    ("qqq_tierA_1h_confirm", "QQQ"),
    ("qqq_midzone_only", "QQQ"),
]

# Baselines for comparison (fib3-equivalent, daily close-in-zone)
BASELINE_EXPERIMENTS = [
    ("spy_tierA_baseline", "SPY"),
    ("xlk_sweep_deep_baseline", "XLK"),
    ("qqq_tierA_baseline", "QQQ"),
]


def get_config(name: str) -> Fib4Config:
    if name not in FIB4_EXPERIMENTS:
        raise KeyError(f"fib4 experiment '{name}' not found. Available: {list(FIB4_EXPERIMENTS)}")
    overrides = FIB4_EXPERIMENTS[name]
    cfg = Fib4Config()
    for key, val in overrides.items():
        if hasattr(cfg, key):
            setattr(cfg, key, val)
    return cfg


def list_experiments() -> list[str]:
    return list(FIB4_EXPERIMENTS.keys())
