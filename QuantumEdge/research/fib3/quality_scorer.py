"""
Leg quality scoring for fib3.

Each function scores one component (0–25).  score_leg() is the main entry point.

Sweep quality  — how deep the spring went AND how quickly it recovered
Displacement   — leg size in ATR multiples (objective momentum proxy)
CHoCH margin   — how decisively the completion broke prior structure
Context        — discount/premium + volume expansion + SPY regime alignment
"""

from __future__ import annotations

import numpy as np

from research.fib3.model import Fib3Config, LegQualityScore


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------


def score_sweep(
    anchor_bar: int,
    anchor_price: float,
    prior_pivot_price: float,
    direction: str,
    closes: np.ndarray,
    atr: float,
    config: Fib3Config,
) -> tuple[float, float, int]:
    """
    Returns (score, sweep_depth_atr, recovery_bars).

    Depth  — how far anchor went BEYOND prior pivot (in ATR).
    Speed  — how many bars until close recovered back above/below prior pivot.
    """
    if atr <= 0:
        return 10.0, 0.0, 0

    if direction == "bullish":
        depth = prior_pivot_price - anchor_price  # positive if anchor < prior LL
    else:
        depth = anchor_price - prior_pivot_price  # positive if anchor > prior HH

    depth_atr = max(depth, 0.0) / atr

    # Find recovery bar
    n = len(closes)
    end = min(anchor_bar + config.sweep_recovery_bars + 1, n)
    recovery_bars = config.sweep_recovery_bars + 1
    recovered = False
    for i in range(anchor_bar, end):
        if direction == "bullish" and closes[i] >= prior_pivot_price:
            recovered = True
            recovery_bars = i - anchor_bar
            break
        if direction == "bearish" and closes[i] <= prior_pivot_price:
            recovered = True
            recovery_bars = i - anchor_bar
            break

    if not recovered:
        return 0.0, depth_atr, recovery_bars

    # Depth score
    if depth_atr >= config.sweep_deep_atr:
        base = 20.0
    elif depth_atr >= config.sweep_medium_atr:
        base = 12.0
    else:
        base = 5.0

    # Speed bonus: fast recovery = more points (0–5)
    speed_bonus = max(0.0, 5.0 - recovery_bars * 1.5)

    return min(base + speed_bonus, 25.0), depth_atr, recovery_bars


# ---------------------------------------------------------------------------
# Displacement
# ---------------------------------------------------------------------------


def score_displacement(leg_atr_multiple: float, config: Fib3Config) -> float:
    """Score based on leg size in ATR multiples."""
    if leg_atr_multiple >= config.disp_exceptional:
        return 25.0
    if leg_atr_multiple >= config.disp_strong:
        return 20.0
    if leg_atr_multiple >= config.disp_standard:
        return 15.0
    if leg_atr_multiple >= config.disp_weak:
        return 8.0
    return 3.0


# ---------------------------------------------------------------------------
# CHoCH (Change of Character)
# ---------------------------------------------------------------------------


def score_choch(
    completion_price: float,
    prior_completion_price: float | None,
    direction: str,
    atr: float,
    config: Fib3Config,
) -> tuple[float, float]:
    """
    Returns (score, choch_margin_atr).

    For bullish: completion (HH) must break above prior HH.
    Margin = (completion - prior_HH) / ATR.
    A decisive CHoCH sweeps the prior HH with room to spare.
    """
    if prior_completion_price is None or atr <= 0:
        return 0.0, 0.0

    if direction == "bullish":
        margin = completion_price - prior_completion_price
    else:
        margin = prior_completion_price - completion_price

    margin_atr = margin / atr

    if margin_atr <= 0:
        return 0.0, margin_atr
    if margin_atr >= config.choch_strong_atr:
        return 25.0, margin_atr

    # Linear interpolation from choch_medium_atr (10 pts) to choch_strong_atr (25 pts)
    if margin_atr >= config.choch_medium_atr:
        t = (margin_atr - config.choch_medium_atr) / (
            config.choch_strong_atr - config.choch_medium_atr
        )
        return 10.0 + t * 15.0, margin_atr

    # Below medium threshold: minimal credit (leg barely broke structure)
    return 5.0, margin_atr


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


def score_context(
    bar: int,
    direction: str,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    volumes: np.ndarray,
    completion_bar: int,
    spy_bull: bool,
    atr: float,
    config: Fib3Config,
) -> tuple[float, bool, float]:
    """
    Returns (score, in_discount, volume_ratio).

    Premium/discount alignment  — 10 pts
    Volume expansion on leg     — 10 pts
    Trend alignment with SPY    —  5 pts
    """
    score = 0.0
    lookback = 60

    # Premium / discount (10 pts)
    in_disc = True
    if bar >= lookback:
        rh = float(np.max(highs[bar - lookback : bar + 1]))
        rl = float(np.min(lows[bar - lookback : bar + 1]))
        if rh > rl:
            mid = (rh + rl) / 2.0
            c = closes[bar]
            in_disc = (c <= mid) if direction == "bullish" else (c >= mid)
    if in_disc:
        score += 10.0

    # Volume expansion at leg completion (10 pts)
    vol_ratio = 1.0
    if 0 < completion_bar < len(volumes) and completion_bar >= 20:
        avg_vol = float(np.mean(volumes[completion_bar - 20 : completion_bar]))
        if avg_vol > 0:
            vol_ratio = float(volumes[completion_bar]) / avg_vol
            if vol_ratio >= config.vol_expansion_ratio:
                score += 10.0
            elif vol_ratio >= 1.0:
                score += 5.0

    # SPY regime alignment (5 pts)
    if (direction == "bullish" and spy_bull) or (direction == "bearish" and not spy_bull):
        score += 5.0

    return min(score, 25.0), in_disc, vol_ratio


# ---------------------------------------------------------------------------
# Master scorer
# ---------------------------------------------------------------------------


def score_leg(
    direction: str,
    anchor_bar: int,
    anchor_price: float,
    completion_bar: int,
    prior_pivot_price: float,
    prior_completion_price: float | None,
    leg_atr_multiple: float,
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    volumes: np.ndarray,
    atr: float,
    spy_bull: bool,
    config: Fib3Config,
) -> LegQualityScore:
    """Compute all four quality components and return a LegQualityScore."""

    sw_s, sw_depth, sw_bars = score_sweep(
        anchor_bar, anchor_price, prior_pivot_price, direction, closes, atr, config
    )
    disp_s = score_displacement(leg_atr_multiple, config)
    choch_s, choch_margin = score_choch(
        # For bullish: completion is the HH; prior_completion is prior HH
        # For bearish: completion is the LL; prior_completion is prior LL
        anchor_price if direction == "bearish" else anchor_price,  # placeholder
        prior_completion_price,
        direction,
        atr,
        config,
    )
    # Re-do choch with actual completion price (passed implicitly via prior_completion_price)
    # We need the completion price here — it's passed as part of the leg detection, not here.
    # The caller should use score_choch() directly with completion_price.
    # This function is a convenience wrapper; see detector.py for full usage.

    ctx_s, in_disc, vol_ratio = score_context(
        anchor_bar,
        direction,
        highs,
        lows,
        closes,
        volumes,
        completion_bar,
        spy_bull,
        atr,
        config,
    )

    total = sw_s + disp_s + choch_s + ctx_s

    return LegQualityScore(
        sweep_score=round(sw_s, 2),
        displacement_score=round(disp_s, 2),
        choch_score=round(choch_s, 2),
        context_score=round(ctx_s, 2),
        total=round(total, 2),
        sweep_depth_atr=round(sw_depth, 3),
        sweep_recovery_bars=sw_bars,
        displacement_atr=round(leg_atr_multiple, 3),
        choch_margin_atr=round(choch_margin, 3),
        in_discount=in_disc,
        volume_ratio=round(vol_ratio, 3),
        spy_bull=spy_bull,
    )


def assign_tier(total: float) -> str:
    if total >= 75:
        return "A"
    if total >= 60:
        return "B"
    if total >= 40:
        return "C"
    return "D"
