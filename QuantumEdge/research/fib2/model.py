"""
Strict Fibonacci manipulation-leg model — data contracts.

CORE THESIS
-----------
A valid manipulation leg is a specific impulse leg that forms after a major
sweep/reversal and creates a displacement move.  The leg retraces into
0.382-0.618 and then extends toward 1.272 and 1.618.

Improvements over fib1
-----------------------
1. SWEEP detection: the anchor pivot must temporarily break a prior structural
   level and recover (spring/upthrust pattern), not merely be a new pivot.
2. DISPLACEMENT requirement: the leg must show strong momentum away from the
   anchor — measured in ATR multiples AND velocity (ATR/bar).
3. MULTI-TIMEFRAME entry: Daily leg defines the trade; 1H (when available) or
   Daily-close (fallback) provides entry confirmation.
4. STOP VARIANTS: origin / 0.786 fib / ATR-based.
5. REGIME FILTERS: SPY 200d SMA, trending ADX-proxy, volume expansion,
   premium/discount context, compression guard.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class StrictFibConfig:
    """All parameters for one strict-model experiment."""

    name: str = "default"

    # ── Timeframe ───────────────────────────────────────────────────────────
    pivot_n: int = 5  # Daily pivot confirmation bars each side
    entry_pivot_n: int = 3  # 1H pivot confirmation bars for structure_shift

    # ── Sweep detection ─────────────────────────────────────────────────────
    require_sweep: bool = True
    # For bullish: LL low must be below prior pivot low (sweep),
    # AND price must close back above prior pivot low within N bars.
    sweep_recovery_bars: int = 3

    # ── Displacement criteria ────────────────────────────────────────────────
    min_displacement_atr: float = 3.0  # Leg in ATR units (vs 1.5 in fib1)
    min_displacement_pct: float = 0.02  # Leg as % of anchor price
    min_leg_bars: int = 3  # Min bars between anchor and completion
    max_leg_bars: int = 120  # Max bars for leg to form
    min_velocity_atr_per_bar: float = 0.0  # Optional: ATR-per-bar velocity check

    # ── Entry zone ───────────────────────────────────────────────────────────
    entry_fib_low: float = 0.382
    entry_fib_high: float = 0.618

    # Entry confirmation variant:
    #   "touch"          — any bar's high/low enters zone (fib1 behaviour)
    #   "close_in_zone"  — daily close inside [fib_low, fib_high]
    #   "rejection"      — bar wicks into zone but closes back above/below midzone
    #   "structure_shift"— local 1H pivot in zone (requires 1H data)
    #   "displacement_off"— strong close above zone_high (bullish)
    entry_confirmation: str = "close_in_zone"

    # ── Stop placement ───────────────────────────────────────────────────────
    # "origin"   — stop just beyond the leg anchor (LL for bull, HH for bear)
    # "fib_786"  — stop just beyond 0.786 retracement
    # "atr_stop" — stop = entry ± atr_stop_multiple * ATR
    stop_variant: str = "origin"
    stop_buffer_atr: float = 0.25  # For origin/fib_786 stops
    atr_stop_multiple: float = 2.0  # For atr_stop variant

    # ── Targets ──────────────────────────────────────────────────────────────
    target_fib: float = 1.618  # 1.272 or 1.618
    scale_at_1272: bool = False  # 50% at 1.272, runner to target_fib

    # ── Trade management ────────────────────────────────────────────────────
    max_zone_wait_bars: int = 40  # Bars to wait for zone entry (entry TF)
    max_bars_in_trade: int = 60  # Max bars in trade (entry TF)

    # ── Risk ─────────────────────────────────────────────────────────────────
    risk_per_trade: float = 0.01
    initial_equity: float = 100_000.0
    atr_period: int = 14

    # ── Directions ───────────────────────────────────────────────────────────
    directions: tuple = ("bullish", "bearish")

    # ── Regime filters (all default off) ────────────────────────────────────
    filter_spy_regime: bool = False  # True = bull only (SPY > 200d SMA)
    filter_spy_regime_bearish: bool = False  # True = bear only (SPY < 200d SMA)
    filter_trending: bool = False  # True = require ADX-proxy trend
    filter_volume_expansion: bool = False  # True = require above-avg volume on leg
    filter_premium_discount: bool = False  # True = require discount(bull)/premium(bear)
    filter_no_compression: bool = False  # True = skip when ATR too tight

    # Compression threshold (ATR as fraction of close)
    compression_atr_pct: float = 0.004  # below this = compressed, skip


@dataclass
class ManipulationLeg:
    """
    A confirmed Daily manipulation leg.

    discovery_bar is the bar after which the leg is fully confirmed and
    no future data was used.  All simulation must start at or after
    discovery_bar.
    """

    direction: str  # "bullish" | "bearish"

    # Anchor and completion bars / prices
    anchor_bar: int  # LL bar (bullish) or HH bar (bearish)
    anchor_price: float  # LL price or HH price
    completion_bar: int  # HH bar (bullish) or LL bar (bearish)
    completion_price: float  # HH price or LL price
    discovery_bar: int  # anchor_bar + pivot_n (when leg is knowable)

    # Prior pivot that was swept (for sweep detection)
    prior_pivot_price: float  # Prior LL (bullish) or prior HH (bearish)
    sweep_confirmed: bool  # Whether anchor qualifies as a sweep

    # Displacement metrics
    leg_points: float
    leg_pct: float
    leg_atr_multiple: float
    velocity_atr_per_bar: float
    atr_at_detection: float

    # Fibonacci levels (computed from anchor→completion)
    fib_0: float  # anchor_price (origin of retracement)
    fib_236: float
    fib_382: float
    fib_50: float
    fib_618: float
    fib_786: float
    fib_100: float  # completion_price
    fib_1272: float
    fib_1618: float

    # Entry zone
    zone_low: float
    zone_high: float

    # Stop price (depends on config.stop_variant, resolved at sim time)
    stop_price_origin: float  # stop if stop_variant="origin"
    stop_price_786: float  # stop if stop_variant="fib_786"


@dataclass
class StrictTradeResult:
    """Result of one simulated trade in the strict model."""

    leg: ManipulationLeg

    entry_bar: int
    entry_price: float
    entry_confirmation_type: str  # Which confirmation triggered

    exit_bar: int
    exit_price: float
    exit_reason: str  # "stop" | "1.272" | "1.618" | "timeout"

    stop_variant_used: str
    stop_price: float
    risk_per_share: float

    r_multiple: float
    mae_r: float  # Max adverse excursion (negative)
    mfe_r: float  # Max favorable excursion (positive)
    bars_held: int

    reached_1272: bool
    reached_1618: bool

    pnl_pct: float
    equity_before: float
    equity_after: float

    # Regime at entry
    spy_bull_regime: bool  # SPY above 200d SMA at entry
    in_trend: bool  # ADX-proxy trending at entry
    volume_expansion: bool  # Volume above 20-bar avg at entry
    in_discount: bool  # Price in discount zone (bullish) or premium (bearish)

    def is_winner(self) -> bool:
        return self.r_multiple > 0

    def is_loser(self) -> bool:
        return self.r_multiple < 0
