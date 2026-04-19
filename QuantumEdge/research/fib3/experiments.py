"""
fib3 experiment configurations.

Naming:
  tier_*    — quality tier filters (primary comparison series)
  choch_*   — CHoCH-focused experiments
  sweep_*   — sweep-focused experiments
  htf_*     — regime + quality combined
  vs_*      — direct comparison pair (broad vs strict quality)
"""

from __future__ import annotations

from research.fib3.model import Fib3Config

FIB3_EXPERIMENTS: dict[str, dict] = {
    # ── Quality tier ladder (primary research series) ─────────────────────
    # All use the same entry/stop/target to isolate leg-quality effect.
    "tier_D_broad": {
        # All legs, no quality gate — equivalent to fib1/fib2 broad baseline
        "name": "tier_D_broad",
        "quality_min_score": 0.0,
        "require_sweep": False,
        "min_displacement_atr": 2.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "tier_C": {
        "name": "tier_C",
        "quality_min_score": 40.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "tier_B": {
        "name": "tier_B",
        "quality_min_score": 60.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    "tier_A": {
        "name": "tier_A",
        "quality_min_score": 75.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    # ── Component isolation: CHoCH alone ─────────────────────────────────
    "choch_decisive": {
        # Only legs where the CHoCH was decisive (≥ 15 CHoCH points)
        "name": "choch_decisive",
        "quality_min_score": 0.0,
        "quality_min_choch": 15.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    # ── Component isolation: Sweep alone ──────────────────────────────────
    "sweep_deep": {
        # Only legs where sweep was deep and fast (≥ 15 sweep points)
        "name": "sweep_deep",
        "quality_min_score": 0.0,
        "quality_min_sweep": 15.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    # ── Best quality + context aligned ────────────────────────────────────
    "tier_A_bull_regime": {
        "name": "tier_A_bull_regime",
        "quality_min_score": 75.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
        "filter_spy_regime": True,
        "directions": ("bullish",),
    },
    # ── Rejection entry on high-quality legs ─────────────────────────────
    "tier_B_rejection": {
        "name": "tier_B_rejection",
        "quality_min_score": 60.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_confirmation": "rejection",
        "stop_variant": "origin",
        "target_fib": 1.618,
    },
    # ── Target at 1.272 (first extension) ────────────────────────────────
    "tier_B_target1272": {
        "name": "tier_B_target1272",
        "quality_min_score": 60.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.272,
    },
    # ── Partial scale: 50% at 1.272, runner to 1.618 ─────────────────────
    "tier_B_scaled": {
        "name": "tier_B_scaled",
        "quality_min_score": 60.0,
        "require_sweep": True,
        "min_displacement_atr": 2.0,
        "entry_confirmation": "close_in_zone",
        "stop_variant": "origin",
        "target_fib": 1.618,
        "scale_at_1272": True,
    },
}


def get_config(name: str) -> Fib3Config:
    if name not in FIB3_EXPERIMENTS:
        raise KeyError(f"fib3 experiment '{name}' not found. Available: {list(FIB3_EXPERIMENTS)}")
    overrides = FIB3_EXPERIMENTS[name]
    cfg = Fib3Config()
    for key, val in overrides.items():
        if hasattr(cfg, key):
            setattr(cfg, key, val)
    return cfg


def list_experiments() -> list[str]:
    return list(FIB3_EXPERIMENTS.keys())
