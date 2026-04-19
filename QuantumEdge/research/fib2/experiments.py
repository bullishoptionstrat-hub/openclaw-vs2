"""
Named experiment configurations for fib2 — strict manipulation-leg model.

Naming convention:
  strict_*      : reference strict configs
  sweep_*       : vary sweep requirement
  disp_*        : vary displacement threshold
  entry_*       : vary entry confirmation
  stop_*        : vary stop placement
  regime_*      : enable regime filters
  compare_*     : direct comparison with fib1 broad model
"""

from __future__ import annotations

from research.fib2.model import StrictFibConfig

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

FIB2_EXPERIMENTS: dict[str, dict] = {
    # ── Strict baseline ───────────────────────────────────────────────────
    "strict_baseline": {
        "name": "strict_baseline",
        "require_sweep": True,
        "min_displacement_atr": 3.0,
        "min_displacement_pct": 0.02,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
        "directions": ("bullish", "bearish"),
    },
    # ── Fib1-equivalent (broad, for direct comparison) ────────────────────
    "broad_fib1_equiv": {
        "name": "broad_fib1_equiv",
        "require_sweep": False,
        "min_displacement_atr": 1.5,
        "min_displacement_pct": 0.015,
        "entry_confirmation": "touch",  # same as fib1 zone_close
        "stop_variant": "origin",
        "target_fib": 1.618,
        "directions": ("bullish", "bearish"),
    },
    # ── Sweep requirement on/off ───────────────────────────────────────────
    "no_sweep": {
        "name": "no_sweep",
        "require_sweep": False,
        "min_displacement_atr": 3.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    # ── Displacement threshold sweep ──────────────────────────────────────
    "disp_2atr": {
        "name": "disp_2atr",
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "disp_4atr": {
        "name": "disp_4atr",
        "require_sweep": True,
        "min_displacement_atr": 4.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "disp_5atr": {
        "name": "disp_5atr",
        "require_sweep": True,
        "min_displacement_atr": 5.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    # ── Entry confirmation variants ───────────────────────────────────────
    "entry_touch": {
        "name": "entry_touch",
        "require_sweep": True,
        "min_displacement_atr": 3.0,
        "entry_confirmation": "touch",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "entry_rejection": {
        "name": "entry_rejection",
        "require_sweep": True,
        "min_displacement_atr": 3.0,
        "entry_confirmation": "rejection",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "entry_displacement_off": {
        "name": "entry_displacement_off",
        "require_sweep": True,
        "min_displacement_atr": 3.0,
        "entry_confirmation": "displacement_off",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    # ── Stop variants ─────────────────────────────────────────────────────
    "stop_fib786": {
        "name": "stop_fib786",
        "require_sweep": True,
        "min_displacement_atr": 3.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "fib_786",
        "target_fib": 1.618,
    },
    "stop_atr2x": {
        "name": "stop_atr2x",
        "require_sweep": True,
        "min_displacement_atr": 3.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "atr_stop",
        "atr_stop_multiple": 2.0,
        "target_fib": 1.618,
    },
    # ── Target variants ───────────────────────────────────────────────────
    "target_1272": {
        "name": "target_1272",
        "require_sweep": True,
        "min_displacement_atr": 3.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.272,
    },
    "target_scaled": {
        "name": "target_scaled",
        "require_sweep": True,
        "min_displacement_atr": 3.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
        "scale_at_1272": True,
    },
    # ── Bullish only ──────────────────────────────────────────────────────
    "strict_bull_only": {
        "name": "strict_bull_only",
        "require_sweep": True,
        "min_displacement_atr": 3.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
        "directions": ("bullish",),
    },
    # ── Regime filters ────────────────────────────────────────────────────
    "regime_spy_bull": {
        "name": "regime_spy_bull",
        "require_sweep": True,
        "min_displacement_atr": 3.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
        "filter_spy_regime": True,
        "directions": ("bullish",),
    },
    "regime_volume": {
        "name": "regime_volume",
        "require_sweep": True,
        "min_displacement_atr": 3.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
        "filter_volume_expansion": True,
    },
    "regime_discount": {
        "name": "regime_discount",
        "require_sweep": True,
        "min_displacement_atr": 3.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
        "filter_premium_discount": True,
        "directions": ("bullish", "bearish"),
    },
    "regime_no_compression": {
        "name": "regime_no_compression",
        "require_sweep": True,
        "min_displacement_atr": 3.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
        "filter_no_compression": True,
    },
    # ── Best-hypothesis combo: strict + bull_only + rejection + origin stop ─
    "best_hypothesis": {
        "name": "best_hypothesis",
        "require_sweep": True,
        "min_displacement_atr": 3.0,
        "entry_confirmation": "rejection",
        "stop_variant": "origin",
        "target_fib": 1.618,
        "scale_at_1272": True,
        "directions": ("bullish",),
        "filter_spy_regime": True,
    },
}


def get_config(name: str) -> StrictFibConfig:
    if name not in FIB2_EXPERIMENTS:
        raise KeyError(f"fib2 experiment '{name}' not found. Available: {list(FIB2_EXPERIMENTS)}")
    overrides = FIB2_EXPERIMENTS[name]
    cfg = StrictFibConfig()
    for key, val in overrides.items():
        if hasattr(cfg, key):
            setattr(cfg, key, val)
    return cfg


def list_experiments() -> list[str]:
    return list(FIB2_EXPERIMENTS.keys())
