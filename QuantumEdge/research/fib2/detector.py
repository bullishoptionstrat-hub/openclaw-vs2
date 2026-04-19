"""
Strict manipulation-leg detector for fib2.

NO-LOOKAHEAD GUARANTEE
  discovery_bar = completion_bar + pivot_n
  All simulation must use only bars[0 : discovery_bar+1].

STRICT LEG CRITERIA (both bullish and bearish)
----------------------------------------------
Bullish:
  1. Anchor (LL) must be a new lower low vs. the prior confirmed pivot low.
  2. SWEEP: anchor candle's low < prior pivot low (automatic if criterion 1 holds),
     AND within `sweep_recovery_bars` bars the close recovers above the prior pivot low.
     If require_sweep=False this check is skipped.
  3. The completion (HH) must be a new higher high vs. the prior confirmed pivot high.
  4. DISPLACEMENT: leg_atr_multiple >= min_displacement_atr
                   leg_pct >= min_displacement_pct
  5. Velocity (optional): leg_points / (hh_bar - ll_bar) >= min_velocity_atr_per_bar * ATR
  6. Leg must span [min_leg_bars, max_leg_bars].

Bearish: mirror of above.
"""

from __future__ import annotations

import numpy as np

from research.fib2.model import StrictFibConfig, ManipulationLeg
from research.fib2.data import compute_atr


# ---------------------------------------------------------------------------
# Pivot detection (same symmetric window as fib1)
# ---------------------------------------------------------------------------


def find_pivots(
    highs: np.ndarray,
    lows: np.ndarray,
    n: int = 5,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """
    Symmetric N-bar pivot detection.
    discovery_bar for pivot at i = i + n.
    """
    size = len(highs)
    pivot_highs: list[tuple[int, float]] = []
    pivot_lows: list[tuple[int, float]] = []

    for i in range(n, size - n):
        # Pivot high
        if highs[i] >= np.max(highs[i - n : i + n + 1]):
            if not np.any(highs[i + 1 : i + n + 1] >= highs[i]):
                pivot_highs.append((i, highs[i]))

        # Pivot low
        if lows[i] <= np.min(lows[i - n : i + n + 1]):
            if not np.any(lows[i + 1 : i + n + 1] <= lows[i]):
                pivot_lows.append((i, lows[i]))

    return pivot_highs, pivot_lows


# ---------------------------------------------------------------------------
# Fibonacci levels
# ---------------------------------------------------------------------------


def _fib_levels_bullish(ll: float, hh: float, stop_buffer: float, atr: float) -> dict:
    span = hh - ll
    return {
        "fib_0": ll,
        "fib_236": ll + 0.236 * span,
        "fib_382": ll + 0.382 * span,
        "fib_50": ll + 0.500 * span,
        "fib_618": ll + 0.618 * span,
        "fib_786": ll + 0.786 * span,
        "fib_100": hh,
        "fib_1272": ll + 1.272 * span,
        "fib_1618": ll + 1.618 * span,
        "stop_origin": max(ll - stop_buffer * atr, ll * 0.97),
        # 0.786 RETRACEMENT stop: 78.6% back from HH toward LL (below the entry zone)
        "stop_786": ll + (1.0 - 0.786) * span - stop_buffer * atr,
    }


def _fib_levels_bearish(hh: float, ll: float, stop_buffer: float, atr: float) -> dict:
    span = hh - ll
    return {
        "fib_0": hh,
        "fib_236": hh - 0.236 * span,
        "fib_382": hh - 0.382 * span,
        "fib_50": hh - 0.500 * span,
        "fib_618": hh - 0.618 * span,
        "fib_786": hh - 0.786 * span,
        "fib_100": ll,
        "fib_1272": hh - 1.272 * span,
        "fib_1618": hh - 1.618 * span,
        "stop_origin": min(hh + stop_buffer * atr, hh * 1.03),
        # 0.786 RETRACEMENT stop: 78.6% back from LL toward HH (above the entry zone)
        "stop_786": hh - (1.0 - 0.786) * span + stop_buffer * atr,
    }


# ---------------------------------------------------------------------------
# Sweep confirmation helper
# ---------------------------------------------------------------------------


def _sweep_confirmed_bullish(
    closes: np.ndarray,
    anchor_bar: int,
    prior_pivot_price: float,
    recovery_bars: int,
) -> bool:
    """
    True if within `recovery_bars` bars starting at anchor_bar,
    the close recovers above prior_pivot_price.
    (The anchor LOW being below prior_pivot_price is already guaranteed
    by the 'new lower low' requirement; we just check for the close recovery.)
    """
    n = len(closes)
    end = min(anchor_bar + recovery_bars + 1, n)
    for i in range(anchor_bar, end):
        if closes[i] >= prior_pivot_price:
            return True
    return False


def _sweep_confirmed_bearish(
    closes: np.ndarray,
    anchor_bar: int,
    prior_pivot_price: float,
    recovery_bars: int,
) -> bool:
    """
    True if within `recovery_bars` bars the close recovers below prior_pivot_price
    (after an upside sweep).
    """
    n = len(closes)
    end = min(anchor_bar + recovery_bars + 1, n)
    for i in range(anchor_bar, end):
        if closes[i] <= prior_pivot_price:
            return True
    return False


# ---------------------------------------------------------------------------
# Main detector
# ---------------------------------------------------------------------------


def find_strict_legs(
    daily_bars: dict,
    config: StrictFibConfig,
) -> list[ManipulationLeg]:
    """
    Detect all strict manipulation legs in the daily bar series.

    Returns legs sorted by discovery_bar.
    """
    highs = daily_bars["highs"]
    lows = daily_bars["lows"]
    closes = daily_bars["closes"]
    n = daily_bars["n"]
    pn = config.pivot_n

    atr_arr = compute_atr(highs, lows, closes, config.atr_period)
    pivot_highs, pivot_lows = find_pivots(highs, lows, pn)

    legs: list[ManipulationLeg] = []

    if "bullish" in config.directions:
        legs.extend(_find_bullish_legs(pivot_highs, pivot_lows, daily_bars, config, atr_arr))
    if "bearish" in config.directions:
        legs.extend(_find_bearish_legs(pivot_highs, pivot_lows, daily_bars, config, atr_arr))

    legs.sort(key=lambda l: l.discovery_bar)
    return legs


# ---------------------------------------------------------------------------
# Bullish legs
# ---------------------------------------------------------------------------


def _find_bullish_legs(
    pivot_highs: list,
    pivot_lows: list,
    bars: dict,
    config: StrictFibConfig,
    atr_arr: np.ndarray,
) -> list[ManipulationLeg]:
    """
    For each LL that sweeps the prior pivot low (new lower low + close recovery):
      find the first qualifying HH (new higher high) → emit one ManipulationLeg.
    """
    highs = bars["highs"]
    lows = bars["lows"]
    closes = bars["closes"]
    pn = config.pivot_n
    results = []

    for ll_idx in range(1, len(pivot_lows)):
        ll_bar, ll_price = pivot_lows[ll_idx]
        prior_ll_bar, prior_ll_price = pivot_lows[ll_idx - 1]

        # Must be a new lower low
        if ll_price >= prior_ll_price:
            continue

        # Sweep check: close must recover above prior LL within recovery_bars
        if config.require_sweep:
            swept = _sweep_confirmed_bullish(
                closes, ll_bar, prior_ll_price, config.sweep_recovery_bars
            )
            if not swept:
                continue

        # Prior HH (for 'new higher high' check on completion)
        prior_hh_price = max(
            (p for b, p in pivot_highs if b < ll_bar),
            default=None,
        )

        for hh_bar, hh_price in pivot_highs:
            if hh_bar <= ll_bar:
                continue

            span = hh_bar - ll_bar
            if span < config.min_leg_bars or span > config.max_leg_bars:
                continue

            # Completion must be a new higher high
            if prior_hh_price is not None and hh_price <= prior_hh_price:
                continue

            discovery_bar = hh_bar + pn
            if discovery_bar >= len(atr_arr):
                continue

            atr = atr_arr[discovery_bar]
            if np.isnan(atr) or atr <= 0:
                continue

            leg_points = hh_price - ll_price
            leg_pct = leg_points / ll_price
            leg_atr = leg_points / atr

            # Displacement filters
            if leg_pct < config.min_displacement_pct:
                break  # No larger HH will fix this for the same LL
            if leg_atr < config.min_displacement_atr:
                continue  # Next HH might be larger

            # Velocity check
            velocity = leg_points / max(span, 1) / atr
            if config.min_velocity_atr_per_bar > 0 and velocity < config.min_velocity_atr_per_bar:
                continue

            fib = _fib_levels_bullish(ll_price, hh_price, config.stop_buffer_atr, atr)

            zone_low = fib["fib_382"]
            zone_high = fib["fib_618"]

            sweep_conf = (
                _sweep_confirmed_bullish(closes, ll_bar, prior_ll_price, config.sweep_recovery_bars)
                if config.require_sweep
                else False
            )

            leg = ManipulationLeg(
                direction="bullish",
                anchor_bar=ll_bar,
                anchor_price=ll_price,
                completion_bar=hh_bar,
                completion_price=hh_price,
                discovery_bar=discovery_bar,
                prior_pivot_price=prior_ll_price,
                sweep_confirmed=sweep_conf,
                leg_points=leg_points,
                leg_pct=leg_pct,
                leg_atr_multiple=leg_atr,
                velocity_atr_per_bar=velocity,
                atr_at_detection=atr,
                fib_0=fib["fib_0"],
                fib_236=fib["fib_236"],
                fib_382=fib["fib_382"],
                fib_50=fib["fib_50"],
                fib_618=fib["fib_618"],
                fib_786=fib["fib_786"],
                fib_100=fib["fib_100"],
                fib_1272=fib["fib_1272"],
                fib_1618=fib["fib_1618"],
                zone_low=zone_low,
                zone_high=zone_high,
                stop_price_origin=fib["stop_origin"],
                stop_price_786=fib["stop_786"],
            )
            results.append(leg)
            break  # One leg per LL

    return results


# ---------------------------------------------------------------------------
# Bearish legs
# ---------------------------------------------------------------------------


def _find_bearish_legs(
    pivot_highs: list,
    pivot_lows: list,
    bars: dict,
    config: StrictFibConfig,
    atr_arr: np.ndarray,
) -> list[ManipulationLeg]:
    """Mirror of _find_bullish_legs for bearish structure."""
    highs = bars["highs"]
    lows = bars["lows"]
    closes = bars["closes"]
    pn = config.pivot_n
    results = []

    for hh_idx in range(1, len(pivot_highs)):
        hh_bar, hh_price = pivot_highs[hh_idx]
        prior_hh_bar, prior_hh_price = pivot_highs[hh_idx - 1]

        if hh_price <= prior_hh_price:
            continue

        if config.require_sweep:
            swept = _sweep_confirmed_bearish(
                closes, hh_bar, prior_hh_price, config.sweep_recovery_bars
            )
            if not swept:
                continue

        prior_ll_price = min(
            (p for b, p in pivot_lows if b < hh_bar),
            default=None,
        )

        for ll_bar, ll_price in pivot_lows:
            if ll_bar <= hh_bar:
                continue

            span = ll_bar - hh_bar
            if span < config.min_leg_bars or span > config.max_leg_bars:
                continue

            if prior_ll_price is not None and ll_price >= prior_ll_price:
                continue

            discovery_bar = ll_bar + pn
            if discovery_bar >= len(atr_arr):
                continue

            atr = atr_arr[discovery_bar]
            if np.isnan(atr) or atr <= 0:
                continue

            leg_points = hh_price - ll_price
            leg_pct = leg_points / hh_price
            leg_atr = leg_points / atr

            if leg_pct < config.min_displacement_pct:
                break
            if leg_atr < config.min_displacement_atr:
                continue

            velocity = leg_points / max(span, 1) / atr
            if config.min_velocity_atr_per_bar > 0 and velocity < config.min_velocity_atr_per_bar:
                continue

            fib = _fib_levels_bearish(hh_price, ll_price, config.stop_buffer_atr, atr)

            # Bearish zone: retracement up from LL toward HH (0.382–0.618 of span above LL)
            zone_low = fib["fib_618"]  # lower bound of retracement zone
            zone_high = fib["fib_382"]  # upper bound of retracement zone

            sweep_conf = (
                _sweep_confirmed_bearish(closes, hh_bar, prior_hh_price, config.sweep_recovery_bars)
                if config.require_sweep
                else False
            )

            leg = ManipulationLeg(
                direction="bearish",
                anchor_bar=hh_bar,
                anchor_price=hh_price,
                completion_bar=ll_bar,
                completion_price=ll_price,
                discovery_bar=discovery_bar,
                prior_pivot_price=prior_hh_price,
                sweep_confirmed=sweep_conf,
                leg_points=leg_points,
                leg_pct=leg_pct,
                leg_atr_multiple=leg_atr,
                velocity_atr_per_bar=velocity,
                atr_at_detection=atr,
                fib_0=fib["fib_0"],
                fib_236=fib["fib_236"],
                fib_382=fib["fib_382"],
                fib_50=fib["fib_50"],
                fib_618=fib["fib_618"],
                fib_786=fib["fib_786"],
                fib_100=fib["fib_100"],
                fib_1272=fib["fib_1272"],
                fib_1618=fib["fib_1618"],
                zone_low=zone_low,
                zone_high=zone_high,
                stop_price_origin=fib["stop_origin"],
                stop_price_786=fib["stop_786"],
            )
            results.append(leg)
            break

    return results
