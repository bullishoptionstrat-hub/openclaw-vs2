"""
Named Experiment Configurations

Each experiment is a dict of config.py overrides.  The runner applies these
on top of the defaults before each Lean run.

Naming convention:  <group>_<variant>
  - baseline_*      : reference configs
  - ablation_*      : one-thing-at-a-time tests
  - alloc_*         : sleeve weight variants
  - rebal_*         : rebalance cadence variants
  - filter_*        : regime filter variants
  - param_*         : parameter sensitivity

ADDING A NEW EXPERIMENT
-----------------------
Add an entry to EXPERIMENTS with a unique key and a dict of overrides.
Only list keys that differ from config.py defaults — everything else
is inherited.
"""

from __future__ import annotations

EXPERIMENTS: dict[str, dict] = {
    # ── Baselines ────────────────────────────────────────────────────────────
    "baseline_a_plus_c": {
        # Current valid local config: Sleeve A + C, B disabled, weights scaled
        "EXPERIMENT_NAME": "baseline_a_plus_c",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": True,
        "ENABLE_LETF_OVERLAY": True,
    },
    "baseline_sectors_only": {
        # Sleeve A alone — all capital in sector momentum
        "EXPERIMENT_NAME": "baseline_sectors_only",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": False,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "ENABLE_LETF_OVERLAY": True,
    },
    "baseline_ibs_only": {
        # Sleeve C alone — all capital in IBS mean reversion
        "EXPERIMENT_NAME": "baseline_ibs_only",
        "ENABLE_SLEEVE_A": False,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "ENABLE_LETF_OVERLAY": False,  # LETF makes no sense without sector regime
    },
    # ── Ablation: regime filter ───────────────────────────────────────────────
    "ablation_no_regime_filter": {
        "EXPERIMENT_NAME": "ablation_no_regime_filter",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
    },
    "ablation_spy_only_regime": {
        # SPY SMA filter only — VXX disabled (removes hidden 2018 data gap)
        "EXPERIMENT_NAME": "ablation_spy_only_regime",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
    },
    "ablation_no_letf": {
        # Test whether SPXU short improves risk-adjusted returns
        "EXPERIMENT_NAME": "ablation_no_letf",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": False,
    },
    "ablation_no_value_tilt": {
        # Pure momentum in Sleeve A — no value blend
        "EXPERIMENT_NAME": "ablation_no_value_tilt",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "VALUE_BLEND": 0.0,
    },
    # ── Sleeve C: IBS contribution ────────────────────────────────────────────
    "ablation_ibs_added": {
        # Sectors + IBS: does IBS add value vs sectors alone?
        # This is the same as baseline_a_plus_c but SPY-only regime
        "EXPERIMENT_NAME": "ablation_ibs_added",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
    },
    # ── Allocation weights ────────────────────────────────────────────────────
    "alloc_60_40": {
        # 60% sectors, 40% IBS
        "EXPERIMENT_NAME": "alloc_60_40",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "SLEEVE_A_ALLOC": 0.60,
        "SLEEVE_C_ALLOC": 0.40,
    },
    "alloc_80_20": {
        # 80% sectors, 20% IBS
        "EXPERIMENT_NAME": "alloc_80_20",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "SLEEVE_A_ALLOC": 0.80,
        "SLEEVE_C_ALLOC": 0.20,
    },
    "alloc_100_sectors": {
        # 100% sectors (pure momentum), no IBS
        "EXPERIMENT_NAME": "alloc_100_sectors",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": False,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "SLEEVE_A_ALLOC": 1.0,
    },
    # ── Top-N sector selection ────────────────────────────────────────────────
    "param_top2_sectors": {
        "EXPERIMENT_NAME": "param_top2_sectors",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "SECTOR_TOP_N": 2,
    },
    "param_top5_sectors": {
        "EXPERIMENT_NAME": "param_top5_sectors",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "SECTOR_TOP_N": 5,
    },
    # ── Rebalance cadence ─────────────────────────────────────────────────────
    "rebal_weekly": {
        # Rebalance every 5 trading days (~weekly)
        "EXPERIMENT_NAME": "rebal_weekly",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "REBAL_DAYS": 5,
    },
    "rebal_monthly": {
        # Rebalance every ~21 trading days (monthly)
        "EXPERIMENT_NAME": "rebal_monthly",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "REBAL_DAYS": 21,
    },
    # ── Parameter sensitivity ─────────────────────────────────────────────────
    "param_mom_3m": {
        # Shorter 3-month momentum window (63 days)
        "EXPERIMENT_NAME": "param_mom_3m",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "MOMENTUM_DAYS": 63,
    },
    "param_mom_12m": {
        # Longer 12-month momentum window (252 days)
        "EXPERIMENT_NAME": "param_mom_12m",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "MOMENTUM_DAYS": 252,
    },
    # ── Named comparison experiments (required by spec) ───────────────────────
    # These are canonical named variants for use in the primary comparison table.
    # Prefer these over the ablation_* variants when presenting results.
    "baseline_full": {
        # Canonical baseline: A+C enabled, B disabled with redistribution, all filters on
        "EXPERIMENT_NAME": "baseline_full",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_UNAVAILABLE_BEHAVIOR": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": False,   # VXX data only from Jan 2018; disabled for clean comparison
        "ENABLE_LETF_OVERLAY": True,
    },
    "no_sleeve_b": {
        # Identical to baseline_full; explicit name for comparison clarity
        "EXPERIMENT_NAME": "no_sleeve_b",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_UNAVAILABLE_BEHAVIOR": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
    },
    "sectors_only": {
        # Sleeve A (sector momentum) only — no IBS, no Greenblatt
        "EXPERIMENT_NAME": "sectors_only",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": False,
        "SLEEVE_B_UNAVAILABLE_BEHAVIOR": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "SLEEVE_A_ALLOC": 1.0,
    },
    "sectors_plus_ibs": {
        # Sleeve A + C — the live-tradeable local config
        "EXPERIMENT_NAME": "sectors_plus_ibs",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_UNAVAILABLE_BEHAVIOR": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
    },
    "regime_filter_off": {
        # No regime filter — always hold equity positions regardless of SPY trend
        "EXPERIMENT_NAME": "regime_filter_off",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_UNAVAILABLE_BEHAVIOR": "redistribute",
        "USE_REGIME_FILTER": False,
        "USE_SPY_SMA_FILTER": False,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
    },
    "fallback_shy": {
        # Sleeve B disabled, but its 40% allocation parked in SHY (not redistributed)
        # Tests the drag of a SHY parking approach vs. redistribution
        "EXPERIMENT_NAME": "fallback_shy",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_UNAVAILABLE_BEHAVIOR": "shy",
        "SLEEVE_B_FALLBACK": "shy",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
    },
    "redistribute_b_to_a_c": {
        # Sleeve B disabled, its 40% redistributed proportionally to A+C
        # Explicit named version of the redistribute behavior
        "EXPERIMENT_NAME": "redistribute_b_to_a_c",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_UNAVAILABLE_BEHAVIOR": "redistribute",
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
    },
    # =========================================================================
    # PHASE 5 — VALIDATED IMPROVEMENTS + SENSITIVITY TESTS
    # =========================================================================
    # Base config for ALL Phase 5 experiments (unless explicitly overridden):
    #   ENABLE_SLEEVE_A=True, ENABLE_SLEEVE_B=False, ENABLE_SLEEVE_C=True
    #   SLEEVE_B_FALLBACK="redistribute"
    #   USE_REGIME_FILTER=True, USE_SPY_SMA_FILTER=True, USE_VXX_FILTER=False
    #   ENABLE_LETF_OVERLAY=True, LETF_WEIGHT=0.05
    #   SECTOR_TOP_N=3, REBAL_DAYS=10, VALUE_BLEND=0.15
    #   SLEEVE_A_ALLOC=0.50, SLEEVE_C_ALLOC=0.10
    # =========================================================================

    # ── Phase 5 anchor ────────────────────────────────────────────────────────
    "baseline_current_best": {
        # Pre-Phase-5 reference point.  Identical to baseline_full.
        # SPY-only regime, top-3 sectors, bi-weekly rebal, 50/10 alloc,
        # VALUE_BLEND=0.15, LETF_WEIGHT=0.05.
        # This IS letf_5 in the LETF sensitivity grid.
        "EXPERIMENT_NAME": "baseline_current_best",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        # All other params at config.py defaults
    },

    # ── Phase 5 combined variant ─────────────────────────────────────────────
    "param_top5_sectors_weekly": {
        # All 4 validated Phase 5 improvements applied together.
        # Change 1: VALUE_BLEND=0.0  (remove value tilt; ablation showed +0.17 Sharpe)
        # Change 2: SECTOR_TOP_N=5   (broader breadth; ablation showed 9.93% CAGR, Sharpe 0.64)
        # Change 3: REBAL_DAYS=5     (weekly; ablation showed Sharpe 0.62)
        # Change 4: SLEEVE_A=0.60, SLEEVE_C=0.40  (60/40 split; ablation showed Sharpe 0.58)
        # Goal: test whether these four improvements compound or partially cancel.
        "EXPERIMENT_NAME": "param_top5_sectors_weekly",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "VALUE_BLEND": 0.0,
        "SECTOR_TOP_N": 5,
        "REBAL_DAYS": 5,
        "SLEEVE_A_ALLOC": 0.60,
        "SLEEVE_C_ALLOC": 0.40,
    },

    # ── Phase 5 decomposition: isolate the alloc contribution ────────────────
    "p5_top5_weekly_no_alloc": {
        # top5 + weekly + no value tilt, but DEFAULT allocation (50/10 pre-scale).
        # Tests whether changing alloc from 50/10 to 60/40 adds incremental value
        # on top of the other three improvements.
        # Compare to: param_top5_sectors_weekly (adds 60/40 alloc change)
        "EXPERIMENT_NAME": "p5_top5_weekly_no_alloc",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "VALUE_BLEND": 0.0,
        "SECTOR_TOP_N": 5,
        "REBAL_DAYS": 5,
        # SLEEVE_A_ALLOC and SLEEVE_C_ALLOC at defaults (0.50, 0.10)
    },

    # ── LETF sensitivity ─────────────────────────────────────────────────────
    # All use baseline_current_best as the base; only LETF varies.
    # letf_5 = baseline_current_best (LETF_WEIGHT=0.05); no separate run needed.
    # ablation_no_letf is close to letf_0 but has SLEEVE_B_FALLBACK set differently —
    # new letf_0 uses explicit base for clean comparison.
    "letf_0": {
        # LETF overlay disabled entirely. Equivalent to LETF_WEIGHT=0 but
        # cleaner: the overlay block is skipped rather than applying a 0-weight short.
        "EXPERIMENT_NAME": "letf_0",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": False,
    },
    "letf_2p5": {
        # LETF_WEIGHT = 0.025 (half the current default)
        "EXPERIMENT_NAME": "letf_2p5",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "LETF_WEIGHT": 0.025,
    },
    "letf_7p5": {
        # LETF_WEIGHT = 0.075 (50% above the current default)
        "EXPERIMENT_NAME": "letf_7p5",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "LETF_WEIGHT": 0.075,
    },

    # ── SECTOR_TOP_N midpoint ─────────────────────────────────────────────────
    "top_n_4_midpoint": {
        # Tests whether N=4 sits between the confirmed N=3 (Sharpe 0.49) and
        # N=5 (Sharpe 0.64) results, or whether it's non-monotonic.
        # Base: baseline_current_best + SECTOR_TOP_N=4 only.
        "EXPERIMENT_NAME": "top_n_4_midpoint",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "SECTOR_TOP_N": 4,
    },
    # ── Phase 6A: LETF extension on combined Phase 5 config ───────────────────
    "letf_10": {
        # LETF_WEIGHT = 0.10 on the Phase 5 combined Sharpe-oriented base.
        # Tests whether the monotonic improvement (letf_0→letf_7p5) continues
        # or inverts.  Base = param_top5_sectors_weekly + LETF_WEIGHT=0.10.
        # Compare against: param_top5_sectors_weekly (LETF_WEIGHT=0.05, Sharpe 0.81)
        "EXPERIMENT_NAME": "letf_10",
        "ENABLE_SLEEVE_A": True,
        "ENABLE_SLEEVE_B": False,
        "ENABLE_SLEEVE_C": True,
        "SLEEVE_B_FALLBACK": "redistribute",
        "USE_REGIME_FILTER": True,
        "USE_SPY_SMA_FILTER": True,
        "USE_VXX_FILTER": False,
        "ENABLE_LETF_OVERLAY": True,
        "LETF_WEIGHT": 0.10,
        "VALUE_BLEND": 0.0,
        "SECTOR_TOP_N": 5,
        "REBAL_DAYS": 5,
        "SLEEVE_A_ALLOC": 0.60,
        "SLEEVE_C_ALLOC": 0.40,
    },
}


def list_experiments() -> list[str]:
    return list(EXPERIMENTS.keys())


def get_experiment(name: str) -> dict:
    if name not in EXPERIMENTS:
        raise KeyError(f"Experiment '{name}' not found. Available: {list(EXPERIMENTS.keys())}")
    return dict(EXPERIMENTS[name])
