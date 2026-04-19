"""
Swing pivot detector and manipulation-leg finder.

NO-LOOKAHEAD GUARANTEE
-----------------------
Pivots use a symmetric N-bar window: a candidate bar i is a pivot high if it has
the highest high in [i-n, i+n].  This window uses n bars on the RIGHT side of the
candidate, so the pivot is only "knowable" at bar i+n.

In the simulation (backtester.py), setups are only activated at
  discovery_bar = hh_bar + pivot_n
which ensures the simulation never uses future data.

For the vectorized detection pass (this file), we run the full dataset in one
pass but record the discovery_bar correctly — the calling simulation must respect
that boundary.
"""

from __future__ import annotations

import numpy as np
from typing import Optional

from research.fib.model import FibModelConfig, ManipulationSetup


# ---------------------------------------------------------------------------
# Step 1 — Pivot detection
# ---------------------------------------------------------------------------


def find_pivots(
    highs: np.ndarray,
    lows: np.ndarray,
    n: int = 5,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """
    Find confirmed pivot highs and lows on an OHLCV bar array.

    A pivot high at bar i is confirmed when bar i+n has been reached:
      highs[i] >= highs[j] for all j in [i-n, i+n] (i != j)

    Ties are broken by NOT marking as pivot (strict inequality on one side
    handles same-price sequences cleanly).

    Parameters
    ----------
    highs, lows : array of bar highs/lows
    n : confirmation bars on each side

    Returns
    -------
    pivot_highs : list of (bar_index, high_price) — actual pivot bar, not discovery bar
    pivot_lows  : list of (bar_index, low_price)
    """
    size = len(highs)
    pivot_highs: list[tuple[int, float]] = []
    pivot_lows: list[tuple[int, float]] = []

    for i in range(n, size - n):
        window_h = highs[i - n : i + n + 1]
        window_l = lows[i - n : i + n + 1]
        center_idx = n  # position of bar i within the window

        # Pivot high: bar i has the highest high in the window (ties go to later bar)
        if highs[i] >= np.max(window_h):
            # Ensure no later bar in the right half ties it (pick rightmost tie)
            right_h = highs[i + 1 : i + n + 1]
            if not np.any(right_h >= highs[i]):
                pivot_highs.append((i, highs[i]))

        # Pivot low: bar i has the lowest low in the window (ties go to later bar)
        if lows[i] <= np.min(window_l):
            right_l = lows[i + 1 : i + n + 1]
            if not np.any(right_l <= lows[i]):
                pivot_lows.append((i, lows[i]))

    return pivot_highs, pivot_lows


# ---------------------------------------------------------------------------
# Step 2 — Fibonacci level calculator
# ---------------------------------------------------------------------------


def _fib_levels_bullish(ll: float, hh: float, stop_buffer_atr: float, atr: float) -> dict:
    """Compute all Fib levels for a bullish leg (anchor=LL, reference=HH)."""
    span = hh - ll
    stop = ll - stop_buffer_atr * atr
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
        "stop_price": max(stop, ll * 0.98),  # never more than 2% below LL
    }


def _fib_levels_bearish(hh: float, ll: float, stop_buffer_atr: float, atr: float) -> dict:
    """Compute all Fib levels for a bearish leg (anchor=HH, reference=LL)."""
    span = hh - ll
    stop = hh + stop_buffer_atr * atr
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
        "stop_price": min(stop, hh * 1.02),
    }


# ---------------------------------------------------------------------------
# Step 3 — Manipulation leg detection
# ---------------------------------------------------------------------------


def find_manipulation_setups(
    bars: dict,
    config: FibModelConfig,
) -> list[ManipulationSetup]:
    """
    Detect all bullish and bearish manipulation-leg setups in the bar series.

    For each qualifying LL→HH (bullish) or HH→LL (bearish) sequence, one
    ManipulationSetup is emitted.  Overlapping legs are allowed but the
    simulation resolves them by time-ordering.

    Timing rule:
      discovery_bar = hh_bar + pivot_n   (bullish)
                    = ll_bar + pivot_n   (bearish)
      No information from bars after discovery_bar is used.

    Parameters
    ----------
    bars : dict from data.load_ticker()
    config : FibModelConfig

    Returns
    -------
    list of ManipulationSetup, sorted by discovery_bar ascending.
    """
    highs = bars["highs"]
    lows = bars["lows"]
    closes = bars["closes"]
    n = bars["n"]

    from research.fib.data import compute_atr

    atr_arr = compute_atr(highs, lows, closes, config.atr_period)

    pivot_highs, pivot_lows = find_pivots(highs, lows, config.pivot_n)

    setups: list[ManipulationSetup] = []

    if "bullish" in config.directions:
        setups.extend(_find_bullish(pivot_highs, pivot_lows, bars, config, atr_arr))
    if "bearish" in config.directions:
        setups.extend(_find_bearish(pivot_highs, pivot_lows, bars, config, atr_arr))

    setups.sort(key=lambda s: s.discovery_bar)
    return setups


def _find_bullish(
    pivot_highs: list,
    pivot_lows: list,
    bars: dict,
    config: FibModelConfig,
    atr_arr: np.ndarray,
) -> list[ManipulationSetup]:
    """
    Bullish manipulation legs: LL (new lower low) followed by HH (new higher high).

    For each LL that is a new structural low:
      1. Find the FIRST qualifying HH (new higher high) that comes AFTER the LL.
      2. Apply quality filters (min leg size, min leg pct, min bars apart).
      3. Record discovery_bar = hh_bar + pivot_n.
    """
    highs = bars["highs"]
    lows = bars["lows"]
    closes = bars["closes"]
    pn = config.pivot_n
    results = []

    for ll_idx in range(1, len(pivot_lows)):
        ll_bar, ll_price = pivot_lows[ll_idx]
        prev_ll_price = pivot_lows[ll_idx - 1][1]

        # LL must be a new lower low (structural break to the downside)
        if ll_price >= prev_ll_price:
            continue

        # Discovery of LL: ll_bar + pn
        ll_discovery = ll_bar + pn

        # Look for HH after the LL
        # "prior HH" = highest pivot high confirmed BEFORE the LL bar
        prior_hh_price = max(
            (p for b, p in pivot_highs if b < ll_bar),
            default=None,
        )

        for hh_bar, hh_price in pivot_highs:
            # HH must come after LL (by actual bar index, not discovery time)
            if hh_bar <= ll_bar:
                continue

            # Minimum separation between LL and HH
            if (hh_bar - ll_bar) < config.min_leg_bars:
                continue

            # HH must be a new higher high (structural break to the upside)
            if prior_hh_price is not None and hh_price <= prior_hh_price:
                continue

            # Discovery bar: when HH confirmation completes
            discovery_bar = hh_bar + pn

            # ATR at discovery
            atr = atr_arr[discovery_bar] if discovery_bar < len(atr_arr) else np.nan
            if np.isnan(atr) or atr <= 0:
                continue

            # Leg quality filters
            leg_points = hh_price - ll_price
            leg_pct = leg_points / ll_price
            leg_atr = leg_points / atr

            if config.min_leg_pct > 0 and leg_pct < config.min_leg_pct:
                break  # no larger HH will fix this; the LL itself is too close

            if config.min_leg_atr > 0 and leg_atr < config.min_leg_atr:
                continue  # next HH might be larger

            # Fibonacci levels
            fib = _fib_levels_bullish(ll_price, hh_price, config.stop_buffer_atr, atr)

            # Entry zone
            zone_low = fib["fib_382"]
            zone_high = fib["fib_618"]
            if config.entry_variant == "golden_only":
                zone_low = fib["fib_50"]

            setup = ManipulationSetup(
                direction="bullish",
                ll_bar=ll_bar,
                ll_price=ll_price,
                hh_bar=hh_bar,
                hh_price=hh_price,
                discovery_bar=discovery_bar,
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
                stop_price=fib["stop_price"],
                leg_points=leg_points,
                leg_pct=leg_pct,
                leg_atr_multiple=leg_atr,
                atr_at_detection=atr,
            )
            results.append(setup)
            break  # one setup per LL; use the first qualifying HH

    return results


def _find_bearish(
    pivot_highs: list,
    pivot_lows: list,
    bars: dict,
    config: FibModelConfig,
    atr_arr: np.ndarray,
) -> list[ManipulationSetup]:
    """
    Bearish manipulation legs: HH (new higher high) followed by LL (new lower low).
    Mirror of _find_bullish.
    """
    highs = bars["highs"]
    lows = bars["lows"]
    pn = config.pivot_n
    results = []

    for hh_idx in range(1, len(pivot_highs)):
        hh_bar, hh_price = pivot_highs[hh_idx]
        prev_hh_price = pivot_highs[hh_idx - 1][1]

        if hh_price <= prev_hh_price:
            continue

        prior_ll_price = min(
            (p for b, p in pivot_lows if b < hh_bar),
            default=None,
        )

        for ll_bar, ll_price in pivot_lows:
            if ll_bar <= hh_bar:
                continue
            if (ll_bar - hh_bar) < config.min_leg_bars:
                continue
            if prior_ll_price is not None and ll_price >= prior_ll_price:
                continue

            discovery_bar = ll_bar + pn

            atr = atr_arr[discovery_bar] if discovery_bar < len(atr_arr) else np.nan
            if np.isnan(atr) or atr <= 0:
                continue

            leg_points = hh_price - ll_price
            leg_pct = leg_points / hh_price
            leg_atr = leg_points / atr

            if config.min_leg_pct > 0 and leg_pct < config.min_leg_pct:
                break
            if config.min_leg_atr > 0 and leg_atr < config.min_leg_atr:
                continue

            fib = _fib_levels_bearish(hh_price, ll_price, config.stop_buffer_atr, atr)

            zone_low = fib["fib_618"]  # bearish zone is ABOVE HH reference (retracement up)
            zone_high = fib["fib_382"]
            if config.entry_variant == "golden_only":
                zone_high = fib["fib_50"]

            setup = ManipulationSetup(
                direction="bearish",
                ll_bar=ll_bar,
                ll_price=ll_price,
                hh_bar=hh_bar,
                hh_price=hh_price,
                discovery_bar=discovery_bar,
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
                stop_price=fib["stop_price"],
                leg_points=leg_points,
                leg_pct=leg_pct,
                leg_atr_multiple=leg_atr,
                atr_at_detection=atr,
            )
            results.append(setup)
            break

    return results
