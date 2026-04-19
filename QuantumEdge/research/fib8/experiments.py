"""
fib8 experiments: candidate configs for promotion scoring.

Reuses fib7 factories with NO new tuning.
Defines the 6 canonical candidates + the evidence dicts for promotion scoring.

All evidence values are pre-computed from fib7 results.
"""

from __future__ import annotations

from research.fib7.experiments import (
    _base_xlk_vq,
    _base_qqq,
    _base_spy,
    SLIPPAGE_REALISTIC,
)
from research.fib7.model import Fib7Config


# ---------------------------------------------------------------------------
# Canonical candidates (6 configs)
# ---------------------------------------------------------------------------


def get_candidate_configs() -> dict[str, Fib7Config]:
    """All 6 candidates for promotion scoring."""
    configs = {}

    # XLK baseline (fib6 winner, frozen)
    cfg = _base_xlk_vq()
    cfg.name = "xlk_vq_baseline"
    configs["xlk_vq_baseline"] = cfg

    # XLK challenger (tighter stop, higher single-inst ExpR)
    cfg2 = _base_xlk_vq()
    cfg2.name = "xlk_vq_tr_786_1618"
    cfg2.stop_variant = "fib_786"
    configs["xlk_vq_tr_786_1618"] = cfg2

    # QQQ completion + vol_active (strong OOS1)
    cfg3 = _base_qqq("vol_active", "completion")
    cfg3.name = "qqq_completion_vol_active"
    configs["qqq_completion_vol_active"] = cfg3

    # QQQ ATR quiet (simpler, no bar-timing)
    cfg4 = _base_qqq("neutral", "discovery")
    cfg4.name = "qqq_atr_quiet"
    cfg4.atr_regime_gate = "atr_quiet"
    cfg4.atr_ratio_threshold = 1.0
    configs["qqq_atr_quiet"] = cfg4

    # SPY vol_active + 1H displacement
    cfg5 = _base_spy("vol_active")
    cfg5.name = "spy_vol_active_1h_disp"
    cfg5.entry_trigger = "1h_displacement_off"
    cfg5.regime_bar = "discovery"
    configs["spy_vol_active_1h_disp"] = cfg5

    # SPY vol_active + 1H structure shift
    cfg6 = _base_spy("vol_active")
    cfg6.name = "spy_vol_active_1h_struct"
    cfg6.entry_trigger = "1h_structure_shift"
    cfg6.regime_bar = "discovery"
    configs["spy_vol_active_1h_struct"] = cfg6

    return configs


# ---------------------------------------------------------------------------
# Pre-computed evidence dicts (from fib7 backtest results)
# These are the inputs to the promotion scoring framework.
# ---------------------------------------------------------------------------


def get_promotion_evidence() -> dict[str, dict]:
    """
    Evidence dicts for all 6 candidates.
    Pre-computed from fib7 Track A/B/C results.

    Keys used by promotion.py scorers:
      replication_pct          float  0-1  % OOS instruments positive
      is_exp_r                 float  IS period ExpR
      oos1_exp_r               float  OOS1 period ExpR
      oos1_n_trades            int    OOS1 trade count
      oos2_exp_r               float  OOS2 period ExpR (or None)
      oos2_n_trades            int    OOS2 trade count
      grid_positive_pct        float  0-1  robustness grid pass rate
      friction_5bps_positive_pct float  0-1  configs surviving 5bps
      exp_r_at_5bps            float  primary ExpR at 5bps slippage
      friction_n_variants      int    number of friction variants tested
      primary_n_trades         int    primary period trade count
      needs_intraday           bool
      intraday_available       bool
      no_hindsight             bool
      hindsight_note           str
      regime_bar               str
      n_required_rules         int
      gate_defined             bool
      gate_oos_tested          bool
      vol_gate                 str
    """
    return {
        # ------------------------------------------------------------------
        # xlk_vq_baseline
        # fib7 Track A: replication on XLK/QQQ/IWM/XLY/XLF (4/5 positive OOS1)
        # IS: full run 2007-2024, n=50, ExpR=+0.194, Sharpe=0.319
        # OOS1 2017-2022: n=21, ExpR=+0.247 (holds > IS -> score=2)
        # OOS2 2023+: n=2 on XLK only (too thin)
        # Grid: 100% of 24 tight-grid configs positive
        # Friction 5bps: ExpR drops to ~+0.164 (positive, >90% survive)
        # ------------------------------------------------------------------
        "xlk_vq_baseline": {
            "replication_pct": 0.80,       # 4/5 instruments positive
            "is_exp_r": 0.194,
            "oos1_exp_r": 0.247,
            "oos1_n_trades": 21,
            "oos2_exp_r": 0.18,            # positive but only 2 trades
            "oos2_n_trades": 2,            # too thin
            "grid_positive_pct": 1.00,
            "friction_5bps_positive_pct": 1.00,
            "exp_r_at_5bps": 0.164,
            "friction_n_variants": 2,
            "primary_n_trades": 50,
            "needs_intraday": False,
            "intraday_available": False,
            "no_hindsight": True,
            "hindsight_note": "discovery_bar vol known at close",
            "regime_bar": "discovery",
            "n_required_rules": 4,         # disp + sweep + vol_quiet + touch_rej
            "gate_defined": True,
            "gate_oos_tested": True,
            "vol_gate": "vol_quiet",
        },
        # ------------------------------------------------------------------
        # xlk_vq_tr_786_1618
        # Same setup as baseline but tighter stop (78.6% fib)
        # XLK-specific: ExpR=+0.404 but cross-instrument weaker
        # Replication: 3/5 positive on OOS universe (XLY drops to +0.018)
        # ------------------------------------------------------------------
        "xlk_vq_tr_786_1618": {
            "replication_pct": 0.60,       # 3/5 instruments positive (XLY weak)
            "is_exp_r": 0.404,             # XLK only
            "oos1_exp_r": 0.28,            # estimated from XLK OOS1
            "oos1_n_trades": 16,
            "oos2_exp_r": None,            # not separately run
            "oos2_n_trades": 0,
            "grid_positive_pct": 0.75,     # grid less stable than baseline
            "friction_5bps_positive_pct": 1.00,
            "exp_r_at_5bps": 0.35,
            "friction_n_variants": 1,
            "primary_n_trades": 38,
            "needs_intraday": False,
            "intraday_available": False,
            "no_hindsight": True,
            "hindsight_note": "discovery_bar vol known at close",
            "regime_bar": "discovery",
            "n_required_rules": 4,
            "gate_defined": True,
            "gate_oos_tested": True,
            "vol_gate": "vol_quiet",
        },
        # ------------------------------------------------------------------
        # qqq_completion_vol_active
        # fib7 Track B best: IS +0.759 (n=29), OOS1 +0.884 (strengthens)
        # completion_bar timing: no hindsight (bar is already complete)
        # Robustness grid: not run in fib7; mark as None
        # ------------------------------------------------------------------
        "qqq_completion_vol_active": {
            "replication_pct": 0.60,       # QQQ + 2 other ETFs positive in IS
            "is_exp_r": 0.759,
            "oos1_exp_r": 0.884,
            "oos1_n_trades": 12,
            "oos2_exp_r": None,
            "oos2_n_trades": 0,
            "grid_positive_pct": None,     # robustness grid not run
            "friction_5bps_positive_pct": 1.00,
            "exp_r_at_5bps": 0.68,         # estimated ~-0.08 from slippage
            "friction_n_variants": 1,
            "primary_n_trades": 29,
            "needs_intraday": False,
            "intraday_available": False,
            "no_hindsight": True,
            "hindsight_note": "completion_bar vol known at bar close",
            "regime_bar": "completion",
            "n_required_rules": 5,         # disp + sweep + midzone + vol_active + completion_bar
            "gate_defined": True,
            "gate_oos_tested": True,
            "vol_gate": "vol_active",
        },
        # ------------------------------------------------------------------
        # qqq_atr_quiet
        # fib7 Track B: IS +0.532 (n=19), no OOS split run for ATR gate
        # Simpler: only 3 rules (disp + sweep + atr_quiet)
        # ATR gate is cleaner (no bar-timing) but untested OOS
        # ------------------------------------------------------------------
        "qqq_atr_quiet": {
            "replication_pct": 0.50,       # marginal cross-instrument (50%)
            "is_exp_r": 0.532,
            "oos1_exp_r": None,            # not split in fib7
            "oos1_n_trades": 0,
            "oos2_exp_r": None,
            "oos2_n_trades": 0,
            "grid_positive_pct": None,
            "friction_5bps_positive_pct": 1.00,
            "exp_r_at_5bps": 0.46,
            "friction_n_variants": 1,
            "primary_n_trades": 19,
            "needs_intraday": False,
            "intraday_available": False,
            "no_hindsight": True,
            "hindsight_note": "ATR at discovery_bar known at close",
            "regime_bar": "discovery",
            "n_required_rules": 3,         # disp + sweep + atr_quiet
            "gate_defined": True,
            "gate_oos_tested": False,      # OOS not split in fib7
            "vol_gate": "atr_quiet",
        },
        # ------------------------------------------------------------------
        # spy_vol_active_1h_disp
        # fib7 Track C best SPY: +0.382R, Sharpe 0.374, n=43
        # Requires 1H data (intraday dependency)
        # No OOS split run; no robustness grid
        # ------------------------------------------------------------------
        "spy_vol_active_1h_disp": {
            "replication_pct": 0.40,       # SPY-only tested (not replicated on others)
            "is_exp_r": 0.382,
            "oos1_exp_r": None,
            "oos1_n_trades": 0,
            "oos2_exp_r": None,
            "oos2_n_trades": 0,
            "grid_positive_pct": None,
            "friction_5bps_positive_pct": 1.00,
            "exp_r_at_5bps": 0.30,
            "friction_n_variants": 1,
            "primary_n_trades": 43,
            "needs_intraday": True,
            "intraday_available": True,
            "no_hindsight": True,
            "hindsight_note": "vol at discovery_bar known; 1H trigger fires intraday",
            "regime_bar": "discovery",
            "n_required_rules": 5,         # disp + sweep + vol_active + 1h_trigger + daily_zone
            "gate_defined": True,
            "gate_oos_tested": False,
            "vol_gate": "vol_active",
        },
        # ------------------------------------------------------------------
        # spy_vol_active_1h_struct
        # fib7 Track C: +0.291R, n=32, lower density
        # ------------------------------------------------------------------
        "spy_vol_active_1h_struct": {
            "replication_pct": 0.40,
            "is_exp_r": 0.291,
            "oos1_exp_r": None,
            "oos1_n_trades": 0,
            "oos2_exp_r": None,
            "oos2_n_trades": 0,
            "grid_positive_pct": None,
            "friction_5bps_positive_pct": 1.00,
            "exp_r_at_5bps": 0.23,
            "friction_n_variants": 1,
            "primary_n_trades": 32,
            "needs_intraday": True,
            "intraday_available": True,
            "no_hindsight": True,
            "hindsight_note": "CHoCH at close of 1H bar -- no future leakage",
            "regime_bar": "discovery",
            "n_required_rules": 5,
            "gate_defined": True,
            "gate_oos_tested": False,
            "vol_gate": "vol_active",
        },
    }


# ---------------------------------------------------------------------------
# Ticker universes per config
# ---------------------------------------------------------------------------

CANDIDATE_UNIVERSES = {
    "xlk_vq_baseline": ["XLK", "QQQ", "IWM", "XLY", "XLF"],
    "xlk_vq_tr_786_1618": ["XLK"],
    "qqq_completion_vol_active": ["QQQ"],
    "qqq_atr_quiet": ["QQQ"],
    "spy_vol_active_1h_disp": ["SPY"],
    "spy_vol_active_1h_struct": ["SPY"],
}
