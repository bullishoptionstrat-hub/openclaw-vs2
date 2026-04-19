"""
fib9 data contracts.

ForwardSetup   -- full state-machine record for one paper-trade setup
CanonicalVerdict -- result of canonical comparison for one instrument
PromotionGateResult -- result of PAPER-LIVE gate check for one config
Fib9Config     -- thin alias of Fib7Config (no new fields needed)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from research.fib7.model import Fib7Config
from research.fib9 import (
    PAPER_LIVE, LIVE_READY, SIGNAL_CARD, PAPER_TRADE,
    CONFLUENCE_ONLY, MAP_ONLY, RESEARCH_ONLY, TIER_ORDER,
)


# ---------------------------------------------------------------------------
# Fib9Config: thin alias
# ---------------------------------------------------------------------------


class Fib9Config(Fib7Config):
    """Identical to Fib7Config -- defined for self-contained fib9 imports."""
    pass


# ---------------------------------------------------------------------------
# Forward state machine states
# ---------------------------------------------------------------------------

SETUP_STATES = frozenset([
    "ARMED",        # detected, zone not yet touched
    "CONFIRMED",    # trigger fired, order ready
    "ENTERED",      # entry fill logged
    "SKIPPED",      # regime gate failed at detection
    "INVALIDATED",  # stop hit before entry
    "STOPPED",      # trade hit stop
    "TARGET_1272",  # first target hit
    "TARGET_1414",  # intermediate target
    "TARGET_1618",  # full target hit
    "EXPIRED",      # max wait bars exceeded
    "CLOSED",       # synonym for terminal trade states
])

TERMINAL_STATES = frozenset([
    "SKIPPED", "INVALIDATED", "STOPPED",
    "TARGET_1272", "TARGET_1414", "TARGET_1618",
    "EXPIRED", "CLOSED",
])

WIN_STATES = frozenset(["TARGET_1272", "TARGET_1414", "TARGET_1618"])
LOSS_STATES = frozenset(["STOPPED", "INVALIDATED"])


# ---------------------------------------------------------------------------
# ForwardSetup dataclass
# ---------------------------------------------------------------------------


@dataclass
class ForwardSetup:
    """Full state-machine record for one paper-trade / forward-replay setup."""

    # Identity
    setup_id: str               # ticker_YYYYMMDD_direction
    ticker: str
    config_name: str

    # Detection
    detection_date: str         # YYYYMMDD -- bar at which leg was detected
    direction: str              # "bullish" | "bearish"

    # Zone geometry
    zone_low: float
    zone_high: float
    fib_382: float
    fib_618: float

    # Risk levels (at detection time)
    stop_price: float
    target_1272: float
    target_1618: float

    # State machine
    state: str = "ARMED"        # current or terminal state

    # Regime snapshot at detection
    regime_at_detection: dict = field(default_factory=dict)
    # keys: vol_ratio, atr_ratio, vol_gate, gate_passed, skip_reason

    # Entry/exit tracking
    trigger_used: str = ""
    skip_reason: str = ""       # non-empty if SKIPPED

    armed_date: str = ""        # = detection_date
    confirm_date: Optional[str] = None
    entry_date: Optional[str] = None
    entry_price: Optional[float] = None
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""       # "stop" | "1.272" | "1.618" | "timeout" | "expired" | "skipped" | "invalidated"

    # Outcome
    outcome_r: Optional[float] = None
    mae_r: Optional[float] = None
    mfe_r: Optional[float] = None

    # Timing
    bars_held: Optional[int] = None
    bars_to_confirm: Optional[int] = None   # detect_bar -> confirm_bar
    bars_to_entry: Optional[int] = None     # detect_bar -> entry_bar

    # Verification
    matched_signal_card: bool = True    # all conditions verified at detection
    notes: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def is_win(self) -> bool:
        return self.state in WIN_STATES

    @property
    def is_loss(self) -> bool:
        return self.state in LOSS_STATES

    @property
    def is_trade(self) -> bool:
        """True if entry was actually taken (not skipped/invalidated/expired)."""
        return self.entry_price is not None


# ---------------------------------------------------------------------------
# CanonicalVerdict dataclass
# ---------------------------------------------------------------------------


@dataclass
class CanonicalVerdict:
    """Result of canonical comparison for one instrument."""

    instrument: str
    winner: str                         # config_name
    runner_up: Optional[str]            # config_name or None
    role: str                           # "PRIMARY" | "MONITORED_ONLY" | "NO_WINNER"
    rationale: str
    per_candidate: dict                 # {config_name: {is_r, oos1_r, oos2_r, n_trades, simplicity_score}}
    decision_standard: str             # description of the rule applied


# ---------------------------------------------------------------------------
# PromotionGateResult dataclass
# ---------------------------------------------------------------------------


@dataclass
class PromotionGateResult:
    """Result of PAPER-LIVE APPROVED gate check."""

    config_name: str
    tier_before: str
    tier_after: str
    passed: bool
    breakdown: dict      # criterion -> bool
    notes: dict          # criterion -> explanation str
    blockers: list       # criterion names that failed
    forward_n: int       # number of forward trades evaluated
    forward_exp_r: Optional[float]
    forward_max_dd: Optional[float]
    armed_to_confirmed_rate: Optional[float]
