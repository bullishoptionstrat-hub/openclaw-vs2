"""
Fibonacci Manipulation-Leg Model — Formal Specification and Configuration
==========================================================================

STRATEGY HYPOTHESIS
-------------------
A recurring institutional market structure pattern exists where:

  1. Price sweeps liquidity below (or above) a prior swing extreme, creating a
     new structural lower low (LL) or higher high (HH).
  2. This sweep is followed by a sharp reversal that establishes a new opposite
     extreme — a higher high (HH) after the bullish sweep, or a lower low (LL)
     after the bearish sweep.
  3. When the resulting LL→HH displacement (bullish) or HH→LL displacement
     (bearish) is measured with Fibonacci ratios:
       - The 0.382–0.618 retracement zone acts as a probabilistic re-entry area.
       - The 1.618 extension acts as a terminal objective for the displacement.

This module tests that hypothesis objectively on historical OHLCV data.

PRECISE SETUP DEFINITION — BULLISH
------------------------------------
Sequence (all pivots must be confirmed — no lookahead):

  Step 1.  A prior pivot high SH_prev is confirmed at bar t1.
  Step 2.  A pivot low LL is confirmed at bar t2 > t1, where:
             LL.price < the most recent prior confirmed pivot low price.
             (i.e., LL is a structural "lower low")
  Step 3.  A pivot high HH is confirmed at bar t3 > t2, where:
             HH.price > the most recent confirmed pivot high price before t2.
             (i.e., HH is a structural "higher high")

  The manipulation leg is the range [LL.price, HH.price].
  Discovery bar = t3 + pivot_n  (the bar when HH confirmation completes).
  No trade information is used before the discovery bar.

PRECISE SETUP DEFINITION — BEARISH
-------------------------------------
Mirror image:

  Step 1.  A prior pivot low SL_prev confirmed at t1.
  Step 2.  A pivot high HH confirmed at t2 > t1, where HH.price > prior pivot high.
  Step 3.  A pivot low LL confirmed at t3 > t2, where LL.price < prior pivot low.

  The manipulation leg is the range [LL.price, HH.price] (same range, opposite direction).

FIBONACCI LEVELS
-----------------
For a bullish leg (anchor = LL, reference = HH):

  Level = LL + ratio × (HH − LL)

  ratio    label       description
  0.000    fib_0       = LL (anchor, invalidation)
  0.236    fib_236     first shallow retracement
  0.382    fib_382     entry zone lower bound
  0.500    fib_50      midpoint
  0.618    fib_618     entry zone upper bound (golden ratio)
  0.786    fib_786     deep retracement
  1.000    fib_100     = HH (reference high)
  1.272    fib_1272    first extension target
  1.618    fib_1618    terminal extension target (golden ratio extension)

For a bearish leg: mirror (entry zone is ABOVE the HH retracement, target is BELOW LL).

ENTRY RULES
------------
After discovery_bar:
  - Monitor for price to enter the entry zone [fib_382, fib_618] (bullish)
    or [1-fib_618, 1-fib_382] (bearish, relative to the leg).
  - Entry variant is set by FibModelConfig.entry_variant:
      'zone_touch'    : enter at OPEN of bar following a close INSIDE the zone
      'zone_close'    : enter at OPEN of bar following a close INSIDE the zone
                        (same as zone_touch but waits for a full close)
      'golden_only'   : enter only at OPEN of bar following close inside [0.50, 0.618]
      'fib_382_touch' : enter at OPEN after price touches 0.382 level

  Entry uses next-bar OPEN to avoid same-bar execution (realistic for daily).

EXIT RULES
-----------
  Stop:   price at or below (bullish) / at or above (bearish) fib_0 (the LL/HH).
          A small buffer (stop_buffer_atr × ATR) can be subtracted.
  Target: configurable — fib_1618, fib_1272, or a scaled exit.
  Timeout: if neither stop nor target is reached within max_bars_in_trade, exit
           at OPEN of bar max_bars_in_trade+1.

INVALIDATION
-------------
  A setup is invalidated (and skipped) if, between discovery_bar and the first
  zone touch:
    - Price breaches fib_0 (the anchor extreme) — stop would be hit anyway.
    - A new conflicting setup is detected (controlled by allow_concurrent flag).
  Invalidated setups are recorded with exit_reason='invalidated_before_entry'.

NO-LOOKAHEAD GUARANTEE
-----------------------
  - Pivots are detected using a symmetric N-bar window [i-n : i+n].
  - A pivot at bar i is only "known" at bar i+n (right-side confirmation delay).
  - discovery_bar = hh_bar + pivot_n (for bullish) or ll_bar + pivot_n (bearish).
  - No OHLCV data from bars > current_bar is ever accessed during simulation.
  - All Fibonacci levels are computed at discovery_bar using only the confirmed
    LL and HH prices, which are from bars < discovery_bar.

MINIMUM QUALITY FILTERS
------------------------
  min_leg_atr      : leg must span at least N × ATR(14) to filter noise.
  min_leg_bars     : LL and HH must be at least N bars apart.
  max_zone_wait    : setup expires if zone is not touched within N bars.

SYMMETRY
---------
  Bearish setups are the exact mirror of bullish setups.
  Both are tested independently and combined.
  The hypothesis should hold symmetrically if the edge is structural.

VALIDITY CRITERIA
------------------
  The hypothesis is considered supported if, across all tested instruments:
    1. Zone hit rate > 50% (price reaches the 0.382–0.618 zone more than half the time).
    2. 1.618 extension hit rate (conditional on zone entry) > 35%.
    3. Expectancy (mean R) > 0 after realistic execution costs.
    4. Results survive out-of-sample testing on a held-out 25% of the date range.
    5. Results are stable across ±20% parameter variation (robustness check).

  The hypothesis is rejected if any of the above are not met across multiple
  instruments, or if results depend on data-mined parameter choices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class FibModelConfig:
    """All parameters for one experimental configuration of the Fib model."""

    # ── Swing detection ─────────────────────────────────────────────────────
    pivot_n: int = 5
    # Number of bars required on each side of a candidate bar for pivot
    # confirmation.  Higher = fewer but more reliable pivots.  Minimum = 2.
    # Introduces a right-side lookahead delay of pivot_n bars.

    # ── Leg quality filters ─────────────────────────────────────────────────
    min_leg_atr: float = 1.5
    # Minimum leg size expressed as multiples of ATR(atr_period) at detection.
    # Filters out tiny noise swings.  0 = disabled.

    atr_period: int = 14
    # ATR rolling window.

    min_leg_bars: int = 3
    # Minimum number of bars between the LL bar and the HH bar.
    # Prevents same-bar or adjacent-bar artifacts.

    min_leg_pct: float = 0.015
    # Minimum leg size as a fraction of the LL price.  e.g., 0.015 = 1.5%.

    # ── Entry ────────────────────────────────────────────────────────────────
    entry_variant: str = "zone_close"
    # 'zone_close'    : enter open of next bar after close inside [fib_382, fib_618]
    # 'golden_only'   : enter open of next bar after close inside [fib_50, fib_618]
    # 'fib_382_touch' : enter open of next bar after LOW touches fib_382 level

    entry_fib_low: float = 0.382
    # Lower bound of entry zone (Fibonacci retracement ratio, 0–1).

    entry_fib_high: float = 0.618
    # Upper bound of entry zone.

    # ── Targets ─────────────────────────────────────────────────────────────
    target_fib: float = 1.618
    # Primary target expressed as a Fibonacci extension ratio.
    # 1.272 = first extension, 1.618 = golden extension.

    scale_at_1272: bool = False
    # If True: take 50% off at 1.272, let remainder run to 1.618.
    # If False: all-or-nothing exit at target_fib.

    # ── Stop ────────────────────────────────────────────────────────────────
    stop_at_fib0: bool = True
    # If True: stop is placed just below fib_0 (the LL for bullish).
    # If False: use stop_atr_buffer * ATR below the zone low (tighter).

    stop_buffer_atr: float = 0.25
    # Extra buffer below fib_0 expressed in ATR multiples.
    # Prevents stop-hunts right at the anchor level.

    # ── Trade management ────────────────────────────────────────────────────
    max_bars_in_trade: int = 60
    # Force-exit if neither stop nor target reached within this many bars.

    max_zone_wait_bars: int = 40
    # Invalidate setup if zone is not touched within this many bars after discovery.

    # ── Position sizing ─────────────────────────────────────────────────────
    risk_per_trade: float = 0.01
    # Fraction of portfolio risked per trade (e.g., 0.01 = 1%).

    initial_equity: float = 100_000.0

    # ── Universe / scope ────────────────────────────────────────────────────
    directions: tuple = ("bullish", "bearish")
    # Which setup directions to test.  ("bullish",) for long-only, etc.

    # ── Experiment identity ──────────────────────────────────────────────────
    name: str = "default"


# ---------------------------------------------------------------------------
# Setup dataclass (a detected but not-yet-traded opportunity)
# ---------------------------------------------------------------------------


@dataclass
class ManipulationSetup:
    direction: str  # 'bullish' or 'bearish'

    # Pivot indices (actual bar indices, before confirmation delay)
    ll_bar: int
    ll_price: float
    hh_bar: int
    hh_price: float

    # The bar index from which we can first act on this setup
    discovery_bar: int

    # Pre-computed Fibonacci levels (at detection time, no lookahead)
    fib_0: float  # anchor extreme (LL for bullish, HH for bearish)
    fib_236: float
    fib_382: float
    fib_50: float
    fib_618: float
    fib_786: float
    fib_100: float  # reference extreme (HH for bullish, LL for bearish)
    fib_1272: float
    fib_1618: float

    # Entry zone bounds (same as fib_382 / fib_618, stored for clarity)
    zone_low: float  # lower bound of entry zone
    zone_high: float  # upper bound of entry zone

    # Stop level
    stop_price: float

    # Quality metrics at detection
    leg_points: float
    leg_pct: float
    leg_atr_multiple: float
    atr_at_detection: float

    # Context
    prior_trend: Optional[str] = None  # 'bull', 'bear', 'neutral'


@dataclass
class TradeResult:
    setup: ManipulationSetup

    # Execution
    entry_bar: int
    entry_price: float

    exit_bar: int
    exit_price: float
    exit_reason: str  # '1.618', '1.272', 'stop', 'timeout', 'invalidated'

    # Risk metrics
    risk_per_share: float  # entry - stop (bullish) or stop - entry (bearish)
    r_multiple: float  # (exit - entry) / risk_per_share (signed)

    mae_r: float  # maximum adverse excursion in R
    mfe_r: float  # maximum favorable excursion in R

    bars_held: int
    reached_1272: bool
    reached_1618: bool

    pnl_pct: float  # percentage return on entry price

    # Portfolio
    equity_before: float
    equity_after: float

    def is_winner(self) -> bool:
        return self.r_multiple > 0

    def is_loser(self) -> bool:
        return self.r_multiple <= 0
