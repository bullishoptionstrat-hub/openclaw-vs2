"""
fib8 data contracts.

No new backtest fields needed -- fib8 re-analyzes fib7 results through the
promotion lens.

PromotionCriteria   -- named constants for the 10 scoring criteria
PromotionScore      -- scored result for one config
Fib8Config          -- thin alias of Fib7Config (no new fields)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from research.fib7.model import Fib7Config


# ---------------------------------------------------------------------------
# Fib8Config: thin alias
# ---------------------------------------------------------------------------


class Fib8Config(Fib7Config):
    """
    fib8 config is identical to Fib7Config.
    Defined as a separate class so imports from fib8 are self-contained.
    """

    pass


# ---------------------------------------------------------------------------
# Promotion tier constants
# ---------------------------------------------------------------------------

RESEARCH_ONLY = "RESEARCH ONLY"
MAP_ONLY = "MAP ONLY"
CONFLUENCE_ONLY = "CONFLUENCE ONLY"
PAPER_TRADE = "PAPER-TRADE CANDIDATE"
SIGNAL_CARD = "SIGNAL-CARD CANDIDATE"
LIVE_READY = "LIVE-READY CANDIDATE"

TIER_ORDER = [LIVE_READY, SIGNAL_CARD, PAPER_TRADE, CONFLUENCE_ONLY, MAP_ONLY, RESEARCH_ONLY]

TIER_THRESHOLDS = [
    (13, LIVE_READY),
    (11, SIGNAL_CARD),
    (9, PAPER_TRADE),
    (7, CONFLUENCE_ONLY),
    (5, MAP_ONLY),
    (0, RESEARCH_ONLY),
]


# ---------------------------------------------------------------------------
# PromotionCriteria: 10 named criteria (key names)
# ---------------------------------------------------------------------------

CRITERION_NAMES = [
    "replication",  # % instruments positive across OOS universe
    "oos1_quality",  # OOS1 positive and doesn't decay >50%
    "oos2_sufficiency",  # OOS2 trade count and sign
    "robustness_plateau",  # % of robustness grid positive
    "friction_survival",  # % survive 5bps friction
    "sample_size",  # primary-period trade count
    "live_feasibility",  # daily-only vs intraday dependency
    "no_hindsight",  # regime gate measured at correct non-future bar
    "rule_simplicity",  # number of required conditions
    "regime_clarity",  # gate defined and OOS tested
]

CRITERION_MAX = {
    "replication": 2,
    "oos1_quality": 2,
    "oos2_sufficiency": 2,
    "robustness_plateau": 2,
    "friction_survival": 2,
    "sample_size": 2,
    "live_feasibility": 2,
    "no_hindsight": 1,
    "rule_simplicity": 1,
    "regime_clarity": 1,
}

MAX_POSSIBLE = sum(CRITERION_MAX.values())  # 17 -- but scoring caps at 14 in practice


# ---------------------------------------------------------------------------
# PromotionScore dataclass
# ---------------------------------------------------------------------------


@dataclass
class PromotionScore:
    """Full promotion scoring result for one config."""

    config_name: str
    tier: str
    total_score: int
    breakdown: dict[str, int]  # criterion -> score
    notes: dict[str, str]  # criterion -> human note
    evidence: dict  # raw evidence used in scoring
    promotion_blockers: list[str]  # criteria scoring 0 that prevent advancement
    upgrade_path: list[str]  # what would add 2+ points
