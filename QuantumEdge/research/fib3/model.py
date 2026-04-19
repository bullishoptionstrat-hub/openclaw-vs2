"""
fib3 data contracts.

Fib3Config   — inherits StrictFibConfig, adds quality + respect params
LegQualityScore — 4-component quality score for a single manipulation leg
QualifiedLeg    — ManipulationLeg fields + prior_completion_price + quality
FibLevelProfile — per-level visit / reaction stats for a single leg
FibRespectProfile — collection of FibLevelProfile for one leg
"""

from __future__ import annotations

from dataclasses import dataclass, field

from research.fib2.model import StrictFibConfig


# ---------------------------------------------------------------------------
# Config (extends StrictFibConfig)
# ---------------------------------------------------------------------------


@dataclass
class Fib3Config(StrictFibConfig):
    """
    All StrictFibConfig fields plus fib3-specific params.

    Leg quality gating:
      quality_min_score  — minimum total score (0–100) to include a leg
      quality_min_sweep  — optional per-component floor
      quality_min_choch  — optional per-component floor

    Quality scoring thresholds:
      sweep_deep_atr     — sweep depth >= N×ATR → max sweep points
      sweep_medium_atr   — intermediate threshold
      disp_exceptional   — leg >= N×ATR → max displacement points
      disp_strong / standard / weak — lower tiers
      choch_strong_atr   — CHoCH margin >= N×ATR → max CHoCH points
      choch_medium_atr   — intermediate threshold
      vol_expansion_ratio— completion-bar vol / 20-bar avg ≥ N → context pts

    Fib respect measurement:
      fib_respect_window    — bars post-discovery to track level visits
      fib_visit_tol_atr     — |bar_range vs level| / ATR < threshold = visit
      fib_react_bars        — bars forward to confirm a reaction after visit
      fib_react_min_atr     — minimum close move (in ATR) to count as reaction
    """

    # ── Looser detector defaults for quality research ──────────────────────
    min_displacement_atr: float = 2.0  # Lower than fib2 to capture all tiers
    min_displacement_pct: float = 0.01

    # ── Quality gating ─────────────────────────────────────────────────────
    quality_min_score: float = 0.0  # Include all tiers by default
    quality_min_sweep: float = 0.0
    quality_min_choch: float = 0.0

    # ── Sweep scoring ──────────────────────────────────────────────────────
    sweep_deep_atr: float = 1.0  # > 1 ATR below prior pivot → full score
    sweep_medium_atr: float = 0.5

    # ── Displacement scoring ───────────────────────────────────────────────
    disp_exceptional: float = 5.0
    disp_strong: float = 4.0
    disp_standard: float = 3.0
    disp_weak: float = 2.0

    # ── CHoCH scoring ──────────────────────────────────────────────────────
    choch_strong_atr: float = 2.0  # completion > 2 ATR above prior HH → full
    choch_medium_atr: float = 0.5

    # ── Context scoring ────────────────────────────────────────────────────
    vol_expansion_ratio: float = 1.3  # completion-bar vol / 20-bar avg

    # ── Fib respect measurement ────────────────────────────────────────────
    fib_respect_window: int = 120  # bars post-discovery to observe
    fib_visit_tol_atr: float = 0.15  # bar touches level if within 15% of ATR
    fib_react_bars: int = 3  # bars after visit to check reaction
    fib_react_min_atr: float = 0.30  # close move >= 30% ATR = valid reaction


# ---------------------------------------------------------------------------
# Quality score
# ---------------------------------------------------------------------------


@dataclass
class LegQualityScore:
    """Four-component quality score for a single manipulation leg."""

    sweep_score: float  # 0–25  spring depth + recovery speed
    displacement_score: float  # 0–25  leg ATR multiple
    choch_score: float  # 0–25  CHoCH decisiveness (margin above prior HH)
    context_score: float  # 0–25  discount/volume/regime alignment

    total: float  # 0–100  sum of above

    # Diagnostic sub-values
    sweep_depth_atr: float = 0.0  # anchor breach below prior pivot (in ATR)
    sweep_recovery_bars: int = 0  # bars until close recovered above prior pivot
    displacement_atr: float = 0.0  # raw leg_atr_multiple
    choch_margin_atr: float = 0.0  # (completion - prior_hh) / ATR
    in_discount: bool = True
    volume_ratio: float = 1.0
    spy_bull: bool = True

    @property
    def tier(self) -> str:
        if self.total >= 75:
            return "A"
        if self.total >= 60:
            return "B"
        if self.total >= 40:
            return "C"
        return "D"


# ---------------------------------------------------------------------------
# Qualified leg (ManipulationLeg + prior_completion_price + quality)
# ---------------------------------------------------------------------------


@dataclass
class QualifiedLeg:
    """
    Complete manipulation leg data with quality score.

    All ManipulationLeg fields are present (duck-typing compatible with
    fib2 backtester).  Additional fields:
      prior_completion_price — prior HH (bullish) or prior LL (bearish)
                               used for CHoCH margin scoring
      quality                — LegQualityScore
    """

    direction: str  # "bullish" | "bearish"

    anchor_bar: int
    anchor_price: float
    completion_bar: int
    completion_price: float
    discovery_bar: int

    prior_pivot_price: float  # Prior LL (bull) / prior HH (bear) — sweep ref
    prior_completion_price: float  # Prior HH (bull) / prior LL (bear) — CHoCH ref
    sweep_confirmed: bool

    leg_points: float
    leg_pct: float
    leg_atr_multiple: float
    velocity_atr_per_bar: float
    atr_at_detection: float

    # Fib levels (same naming as ManipulationLeg for duck-type compatibility)
    fib_0: float
    fib_236: float
    fib_382: float
    fib_50: float
    fib_618: float
    fib_786: float
    fib_100: float
    fib_1272: float
    fib_1618: float

    # fib3-exclusive levels
    fib_1414: float

    zone_low: float
    zone_high: float
    stop_price_origin: float
    stop_price_786: float

    quality: LegQualityScore


# ---------------------------------------------------------------------------
# Fib respect profile
# ---------------------------------------------------------------------------

FIB_LEVEL_KEYS = [
    "ret_0236",  # HH - 0.236 * span  (shallow retracement)
    "ret_0382",  # HH - 0.382 * span  = fib2 fib_618
    "ret_0500",  # HH - 0.500 * span  = fib2 fib_50
    "ret_0618",  # HH - 0.618 * span  = fib2 fib_382
    "ret_0786",  # HH - 0.786 * span  (deep retracement, below entry zone)
    "ext_1272",  # LL + 1.272 * span
    "ext_1414",  # LL + 1.414 * span
    "ext_1618",  # LL + 1.618 * span
]

# Human-readable display labels
FIB_LEVEL_LABELS = {
    "ret_0236": "0.236 ret",
    "ret_0382": "0.382 ret",
    "ret_0500": "0.500 ret",
    "ret_0618": "0.618 ret",
    "ret_0786": "0.786 ret",
    "ext_1272": "1.272 ext",
    "ext_1414": "1.414 ext",
    "ext_1618": "1.618 ext",
}


@dataclass
class FibLevelProfile:
    """Per-level observation for a single leg within the observation window."""

    level_key: str
    level_price: float
    visited: bool = False  # Price came within visit tolerance
    reacted: bool = False  # Directional reaction after visit
    min_proximity_atr: float = 99.0  # Closest price came to this level (in ATR)
    visit_bar: int = -1  # Bar index of first visit (-1 = never)


@dataclass
class FibRespectProfile:
    """Fib level observations for one QualifiedLeg."""

    direction: str
    discovery_bar: int
    quality_score: float
    quality_tier: str
    levels: dict = field(default_factory=dict)  # key → FibLevelProfile
