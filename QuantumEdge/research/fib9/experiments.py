"""
fib9 candidate configs.

Defines the per-instrument candidate sets for canonical comparison.
Reuses fib7/fib8 config factories -- NO new tuning.

XLK: xlk_vq_baseline, xlk_vq_tr_786_1618
QQQ: qqq_completion_vol_active, qqq_atr_quiet, qqq_discovery_neutral
SPY: spy_vol_active_1h_disp, spy_neutral_tr

OOS splits: IS=2007-2016, OOS1=2017-2022, OOS2=2023+
"""

from __future__ import annotations

from research.fib7.model import Fib7Config
from research.fib7.experiments import (
    _base_xlk_vq,
    _base_qqq,
    _base_spy,
    SLIPPAGE_REALISTIC,
)


# ---------------------------------------------------------------------------
# Instrument groupings
# ---------------------------------------------------------------------------

CANONICAL_TICKERS = ["XLK", "QQQ", "SPY"]
ROTATION_UNIVERSE = ["XLK", "QQQ", "IWM", "XLY", "XLF"]

# OOS periods (used in canonical.py and forward_replay.py)
IS_START = "20070101"
IS_END = "20161231"
OOS1_START = "20170101"
OOS1_END = "20221231"
OOS2_START = "20230101"
OOS2_END = None  # present


# ---------------------------------------------------------------------------
# Per-instrument candidate sets
# ---------------------------------------------------------------------------


def get_xlk_candidates() -> dict[str, Fib7Config]:
    """XLK candidate configs for canonical comparison."""
    configs = {}

    # Baseline: frozen fib6 winner
    cfg = _base_xlk_vq()
    cfg.name = "xlk_vq_baseline"
    # Wire in OOS splits
    cfg.is_start = IS_START
    cfg.is_end = IS_END
    cfg.oos1_start = OOS1_START
    cfg.oos1_end = OOS1_END
    cfg.oos2_start = OOS2_START
    cfg.oos2_end = OOS2_END
    configs["xlk_vq_baseline"] = cfg

    # Challenger: tighter stop, higher single-inst ExpR
    cfg2 = _base_xlk_vq()
    cfg2.name = "xlk_vq_tr_786_1618"
    cfg2.stop_variant = "fib_786"
    cfg2.is_start = IS_START
    cfg2.is_end = IS_END
    cfg2.oos1_start = OOS1_START
    cfg2.oos1_end = OOS1_END
    cfg2.oos2_start = OOS2_START
    cfg2.oos2_end = OOS2_END
    configs["xlk_vq_tr_786_1618"] = cfg2

    return configs


def get_qqq_candidates() -> dict[str, Fib7Config]:
    """QQQ candidate configs for canonical comparison."""
    configs = {}

    # Best OOS1: completion bar + vol_active
    cfg = _base_qqq("vol_active", "completion")
    cfg.name = "qqq_completion_vol_active"
    cfg.is_start = IS_START
    cfg.is_end = IS_END
    cfg.oos1_start = OOS1_START
    cfg.oos1_end = OOS1_END
    cfg.oos2_start = OOS2_START
    cfg.oos2_end = OOS2_END
    configs["qqq_completion_vol_active"] = cfg

    # Simpler: ATR quiet gate (no bar-timing dependency)
    cfg2 = _base_qqq("neutral", "discovery")
    cfg2.name = "qqq_atr_quiet"
    cfg2.atr_regime_gate = "atr_quiet"
    cfg2.atr_ratio_threshold = 1.0
    cfg2.is_start = IS_START
    cfg2.is_end = IS_END
    cfg2.oos1_start = OOS1_START
    cfg2.oos1_end = OOS1_END
    cfg2.oos2_start = OOS2_START
    cfg2.oos2_end = OOS2_END
    configs["qqq_atr_quiet"] = cfg2

    # Control baseline: neutral gate (no filtering)
    cfg3 = _base_qqq("neutral", "discovery")
    cfg3.name = "qqq_discovery_neutral"
    cfg3.is_start = IS_START
    cfg3.is_end = IS_END
    cfg3.oos1_start = OOS1_START
    cfg3.oos1_end = OOS1_END
    cfg3.oos2_start = OOS2_START
    cfg3.oos2_end = OOS2_END
    configs["qqq_discovery_neutral"] = cfg3

    return configs


def get_spy_candidates() -> dict[str, Fib7Config]:
    """SPY candidate configs for canonical comparison."""
    configs = {}

    # Best SPY from fib7 Track C: vol_active + 1H displacement
    cfg = _base_spy("vol_active")
    cfg.name = "spy_vol_active_1h_disp"
    cfg.entry_trigger = "1h_displacement_off"
    cfg.is_start = IS_START
    cfg.is_end = IS_END
    cfg.oos1_start = OOS1_START
    cfg.oos1_end = OOS1_END
    cfg.oos2_start = OOS2_START
    cfg.oos2_end = OOS2_END
    configs["spy_vol_active_1h_disp"] = cfg

    # Neutral control: daily touch_rejection, no vol gate
    cfg2 = _base_spy("neutral")
    cfg2.name = "spy_neutral_tr"
    cfg2.entry_trigger = "touch_rejection"
    cfg2.is_start = IS_START
    cfg2.is_end = IS_END
    cfg2.oos1_start = OOS1_START
    cfg2.oos1_end = OOS1_END
    cfg2.oos2_start = OOS2_START
    cfg2.oos2_end = OOS2_END
    configs["spy_neutral_tr"] = cfg2

    return configs


def get_all_candidates() -> dict[str, dict[str, Fib7Config]]:
    """All candidates grouped by instrument."""
    return {
        "XLK": get_xlk_candidates(),
        "QQQ": get_qqq_candidates(),
        "SPY": get_spy_candidates(),
    }


def get_canonical_forward_set() -> dict[str, Fib7Config]:
    """
    Canonical configs for forward replay and signal export.
    Keys are config names, each with its primary ticker embedded.
    Updated by canonical.py after canonical freeze — these are pre-hypothesized defaults.
    """
    xlk = get_xlk_candidates()["xlk_vq_baseline"]
    qqq = get_qqq_candidates()["qqq_completion_vol_active"]
    spy = get_spy_candidates()["spy_vol_active_1h_disp"]
    return {
        "xlk_vq_baseline": xlk,
        "qqq_completion_vol_active": qqq,
        "spy_vol_active_1h_disp": spy,
    }


# Ticker mapping for forward replay
CANONICAL_TICKER_MAP = {
    "xlk_vq_baseline": "XLK",
    "xlk_vq_tr_786_1618": "XLK",
    "qqq_completion_vol_active": "QQQ",
    "qqq_atr_quiet": "QQQ",
    "qqq_discovery_neutral": "QQQ",
    "spy_vol_active_1h_disp": "SPY",
    "spy_neutral_tr": "SPY",
}

# Simplicity scores (lower = simpler, used in canonical decision)
SIMPLICITY_SCORES = {
    "xlk_vq_baseline": 1,           # 4 rules, daily only
    "xlk_vq_tr_786_1618": 2,        # same rules, tighter stop (implementation risk)
    "qqq_completion_vol_active": 3,  # 5 rules, completion-bar timing dependency
    "qqq_atr_quiet": 2,             # 3 rules, daily only, no bar-timing
    "qqq_discovery_neutral": 1,     # 3 rules, no regime gate
    "spy_vol_active_1h_disp": 4,    # 5 rules + intraday dependency
    "spy_neutral_tr": 1,            # 3 rules, daily only
}
