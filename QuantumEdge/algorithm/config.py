"""
QuantumEdge — Central Configuration
=====================================
All parameters, feature flags, and allocation weights live here.
Edit this file (or override via experiment_config.json) to run ablation tests
without touching algorithm logic.

DESIGN RULES:
- No magic numbers anywhere else in the codebase.
- Booleans for feature flags, floats for weights/params.
- Allocation weights do NOT need to sum to 1.0; the Allocator normalises them
  based on which sleeves are enabled.
- Any parameter that affects backtest results must be defined here.
"""

import json
import os

# ---------------------------------------------------------------------------
# FEATURE FLAGS
# ---------------------------------------------------------------------------

ENABLE_SLEEVE_A       = True
# SLEEVE B DISABLED: requires QuantConnect coarse/fine fundamental data.
# That data is NOT available in local Lean setup. Enabling this without the
# data silently parks 40% of the portfolio in SHY for the entire backtest.
# Status: "LOCAL_DATA_UNAVAILABLE" — do not enable until fundamental data
# is sourced from QuantConnect cloud or a local EDGAR-based alternative.
ENABLE_SLEEVE_B       = False

ENABLE_SLEEVE_C       = True

USE_REGIME_FILTER     = True
USE_SPY_SMA_FILTER    = True   # primary regime: SPY > 200d SMA
USE_VXX_FILTER        = True   # secondary: VXX < 20d SMA (degrades if VXX absent)

ENABLE_LETF_OVERLAY   = True   # short SPXU in uptrend only

# What to do with Sleeve B's allocation when it is disabled or data is absent:
#   "redistribute"  — scale A + C proportionally to fill the gap (recommended)
#   "shy"           — explicitly park Sleeve B allocation in FALLBACK_ASSET
SLEEVE_B_FALLBACK     = "redistribute"

# What to do when Sleeve B is ENABLED (ENABLE_SLEEVE_B=True) but the required
# QuantConnect coarse/fine fundamental data is NOT present in the local dataset.
# This is distinct from SLEEVE_B_FALLBACK which handles the disabled case.
#   "redistribute"  — disable B, scale A+C to 100% (recommended for local runs)
#   "shy"           — park Sleeve B allocation in FALLBACK_ASSET
#   "fail"          — raise RuntimeError immediately; do not run the backtest
SLEEVE_B_UNAVAILABLE_BEHAVIOR = "redistribute"

FALLBACK_ASSET        = "SHY"  # safe-haven when not in equity mode or fallback

# ---------------------------------------------------------------------------
# BACKTEST DATES
# ---------------------------------------------------------------------------

START_YEAR, START_MONTH, START_DAY = 2013, 1, 1
END_YEAR,   END_MONTH,   END_DAY   = 2023, 12, 31
INITIAL_CASH = 100_000

# ---------------------------------------------------------------------------
# SLEEVE A — SECTOR MOMENTUM + VALUE TILT
# ---------------------------------------------------------------------------

SECTORS = [
    "XLK",   # Technology
    "XLV",   # Health Care
    "XLF",   # Financials
    "XLI",   # Industrials
    "XLY",   # Consumer Discretionary
    "XLP",   # Consumer Staples
    "XLE",   # Energy
    "XLB",   # Materials
    "XLU",   # Utilities
    "XLC",   # Communication Services  [data from 2018-06-19 locally]
    "XLRE",  # Real Estate             [data from 2015-10-08 locally]
]

SECTOR_TOP_N    = 3       # hold top-N ranked sectors
MOMENTUM_DAYS   = 126     # 6-month lookback for cross-sectional momentum
MOMENTUM_SKIP   = 21      # [NOT YET IMPLEMENTED] intended to skip last month
                           # to reduce 1-month reversal; tracked as tech-debt
VALUE_BLEND     = 0.15    # weight of value tilt in composite sector score
VALUE_LOOKBACK  = 504     # ~2 years; relative sector return used as value proxy
                           # NOTE: this is a medium-term momentum inversion,
                           # not a fundamental value signal — label accordingly

# ---------------------------------------------------------------------------
# SLEEVE B — GREENBLATT MAGIC FORMULA (DISABLED LOCALLY)
# ---------------------------------------------------------------------------

GREENBLATT_N_COARSE     = 500   # coarse universe size
GREENBLATT_N_EVEBITDA   = 20    # pre-filter by EV/EBITDA rank before ROC sort
GREENBLATT_N_PORTFOLIO  = 10    # final stock picks

# ---------------------------------------------------------------------------
# SLEEVE C — IBS MEAN REVERSION
# ---------------------------------------------------------------------------

IBS_ETFS = [
    "EWA",  # Australia
    "EWC",  # Canada
    "EWG",  # Germany
    "EWH",  # Hong Kong
    "EWJ",  # Japan
    "EWY",  # South Korea
    "EWZ",  # Brazil
    "EWT",  # Taiwan
    "EWU",  # United Kingdom
    "EWI",  # Italy
    "FXI",  # China
    "THD",  # Thailand
]

IBS_TOP_N = 2   # long N most oversold + short N most overbought

# ---------------------------------------------------------------------------
# SLEEVE ALLOCATION WEIGHTS
# The Allocator normalises these based on which sleeves are ENABLED.
# Example: if Sleeve B disabled, effective_a = 0.50/(0.50+0.10) = 83.3%
#          effective_c = 0.10/(0.50+0.10) = 16.7%
# ---------------------------------------------------------------------------

SLEEVE_A_ALLOC  = 0.50
SLEEVE_B_ALLOC  = 0.40   # only used if ENABLE_SLEEVE_B = True
SLEEVE_C_ALLOC  = 0.10

# ---------------------------------------------------------------------------
# LETF OVERLAY
# ---------------------------------------------------------------------------

LETF_TICKER     = "SPXU"   # 3x inverse S&P 500
LETF_WEIGHT     = 0.05     # fraction of portfolio shorted (margin-funded)
                            # only applied when equity regime is active

# ---------------------------------------------------------------------------
# RISK CONTROLS
# ---------------------------------------------------------------------------

RISK_VOL_LB     = 20    # rolling realized-vol window for risk-parity sizing
TREND_SMA_DAYS  = 200   # SPY SMA period for primary regime filter
VXX_SMA_DAYS    = 20    # VXX SMA period for secondary regime filter
REBAL_DAYS      = 10    # rebalance every N trading days (~bi-weekly)
MAX_POSITION    = 0.20  # single-name weight cap (hard)
CHURN_THRESHOLD = 0.01  # skip set_holdings if |current_w - target_w| < this

# ---------------------------------------------------------------------------
# WARMUP
# ---------------------------------------------------------------------------

WARMUP_DAYS = 150   # bars before first trade is allowed

# ---------------------------------------------------------------------------
# EXPERIMENT IDENTITY
# Set by research/runner.py before each run.
# Used to label output files.
# ---------------------------------------------------------------------------

EXPERIMENT_NAME = "default"

# ---------------------------------------------------------------------------
# OVERRIDE LOADER
# If QuantumEdge/experiment_config.json exists, its values override defaults.
# The research runner writes this file before each experiment run.
# ---------------------------------------------------------------------------

def _load_overrides() -> dict:
    override_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "experiment_config.json",
    )
    if os.path.exists(override_path):
        with open(override_path) as f:
            return json.load(f)
    return {}


def apply_overrides(module_globals: dict) -> list[str]:
    """
    Apply experiment_config.json overrides to the calling module's globals.
    Returns list of keys that were overridden (for logging).
    Call once at the bottom of config.py or at algorithm init.
    """
    overrides = _load_overrides()
    applied = []
    for key, value in overrides.items():
        if key in module_globals:
            module_globals[key] = value
            applied.append(key)
    return applied


# Apply overrides immediately when this module is imported
_overridden = apply_overrides(globals())
