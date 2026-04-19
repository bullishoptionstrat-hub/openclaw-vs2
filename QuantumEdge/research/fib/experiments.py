"""
Named experiment configurations for the Fibonacci manipulation-leg model.

Each entry is a dict of FibModelConfig field overrides.
Only fields that differ from the FibModelConfig defaults need to be listed.

Naming convention:
  baseline_*     : reference configs with standard parameters
  entry_*        : vary the entry variant
  target_*       : vary the exit target
  pivot_n_*      : vary the pivot confirmation window
  leg_*          : vary leg quality filters
  direction_*    : long-only or short-only subsets
"""

from __future__ import annotations

from research.fib.model import FibModelConfig

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

FIB_EXPERIMENTS: dict[str, dict] = {
    # ── Baselines ──────────────────────────────────────────────────────────
    "baseline_both": {
        # Default config, both directions, 0.382–0.618 zone, 1.618 target
        "name": "baseline_both",
        "directions": ("bullish", "bearish"),
        "entry_variant": "zone_close",
        "entry_fib_low": 0.382,
        "entry_fib_high": 0.618,
        "target_fib": 1.618,
        "pivot_n": 5,
    },
    "baseline_bullish_only": {
        "name": "baseline_bullish_only",
        "directions": ("bullish",),
        "entry_variant": "zone_close",
        "target_fib": 1.618,
        "pivot_n": 5,
    },
    "baseline_bearish_only": {
        "name": "baseline_bearish_only",
        "directions": ("bearish",),
        "entry_variant": "zone_close",
        "target_fib": 1.618,
        "pivot_n": 5,
    },
    # ── Entry variant sweep ────────────────────────────────────────────────
    "entry_golden_only": {
        # Narrower zone: only enter at [0.50, 0.618] (golden retracement)
        "name": "entry_golden_only",
        "directions": ("bullish", "bearish"),
        "entry_variant": "golden_only",
        "entry_fib_low": 0.50,
        "entry_fib_high": 0.618,
        "target_fib": 1.618,
    },
    "entry_fib382_touch": {
        # Enter when the low/high touches 0.382 exactly (less filtering)
        "name": "entry_fib382_touch",
        "directions": ("bullish", "bearish"),
        "entry_variant": "fib_382_touch",
        "target_fib": 1.618,
    },
    # ── Target sweep ──────────────────────────────────────────────────────
    "target_1272": {
        # Tighter target at 1.272 instead of 1.618
        "name": "target_1272",
        "directions": ("bullish", "bearish"),
        "entry_variant": "zone_close",
        "target_fib": 1.272,
    },
    "target_1618_scaled": {
        # Scale: 50% at 1.272, 50% at 1.618
        "name": "target_1618_scaled",
        "directions": ("bullish", "bearish"),
        "entry_variant": "zone_close",
        "target_fib": 1.618,
        "scale_at_1272": True,
    },
    # ── Pivot N sweep ──────────────────────────────────────────────────────
    "pivot_n3": {
        "name": "pivot_n3",
        "directions": ("bullish", "bearish"),
        "entry_variant": "zone_close",
        "target_fib": 1.618,
        "pivot_n": 3,
    },
    "pivot_n8": {
        "name": "pivot_n8",
        "directions": ("bullish", "bearish"),
        "entry_variant": "zone_close",
        "target_fib": 1.618,
        "pivot_n": 8,
    },
    # ── Leg quality filter sweep ───────────────────────────────────────────
    "leg_loose": {
        # Minimal quality filters — capture more setups, potentially noisier
        "name": "leg_loose",
        "directions": ("bullish", "bearish"),
        "entry_variant": "zone_close",
        "target_fib": 1.618,
        "min_leg_atr": 0.5,
        "min_leg_pct": 0.005,
        "min_leg_bars": 2,
    },
    "leg_strict": {
        # High quality filter — fewer but higher-quality setups
        "name": "leg_strict",
        "directions": ("bullish", "bearish"),
        "entry_variant": "zone_close",
        "target_fib": 1.618,
        "min_leg_atr": 3.0,
        "min_leg_pct": 0.03,
        "min_leg_bars": 5,
    },
}


def get_fib_config(name: str) -> FibModelConfig:
    """Build a FibModelConfig from the named experiment overrides."""
    if name not in FIB_EXPERIMENTS:
        available = list(FIB_EXPERIMENTS.keys())
        raise KeyError(f"Fib experiment '{name}' not found.  Available: {available}")
    overrides = FIB_EXPERIMENTS[name]
    cfg = FibModelConfig()
    for key, value in overrides.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    return cfg


def list_fib_experiments() -> list[str]:
    return list(FIB_EXPERIMENTS.keys())
