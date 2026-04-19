"""
Fib level respect analyzer for fib3.

For each QualifiedLeg, measures within a post-discovery observation window:
  - Whether price VISITED each of the 8 standard fib levels
  - Whether price REACTED (bounced or extended) after that visit

Level conventions (bullish leg: LL → HH, span = HH - LL):
  Retracement levels (measured from HH back toward LL):
    ret_0236 = HH - 0.236 * span   (shallow pullback)
    ret_0382 = HH - 0.382 * span   (= fib2 fib_618 / entry zone top)
    ret_0500 = HH - 0.500 * span   (equilibrium)
    ret_0618 = HH - 0.618 * span   (= fib2 fib_382 / entry zone bottom)
    ret_0786 = HH - 0.786 * span   (deep pullback, below entry zone)

  Extension levels (measured from LL through and beyond HH):
    ext_1272 = LL + 1.272 * span
    ext_1414 = LL + 1.414 * span
    ext_1618 = LL + 1.618 * span

  Bearish: all directions mirrored.

"Visit":  a daily bar's range overlaps the ±tolerance band around the level.
"React":  within fib_react_bars bars after the visit, price moves >= fib_react_min_atr
          in the EXPECTED direction (bounce for retracement, continuation for extension).
"""

from __future__ import annotations

import numpy as np

from research.fib3.model import (
    Fib3Config,
    QualifiedLeg,
    FibLevelProfile,
    FibRespectProfile,
    FIB_LEVEL_KEYS,
)


# ---------------------------------------------------------------------------
# Level computation
# ---------------------------------------------------------------------------


def compute_standard_levels(leg: QualifiedLeg) -> dict[str, float]:
    """
    Return the 8 standard level prices for this leg using correct convention.

    All computed from first principles — not using fib2's named fields
    to avoid the fib_382 / 0.618-retracement naming ambiguity.
    """
    if leg.direction == "bullish":
        ll = leg.fib_0  # anchor = LL
        hh = leg.fib_100  # completion = HH
        span = hh - ll
        return {
            "ret_0236": hh - 0.236 * span,
            "ret_0382": hh - 0.382 * span,
            "ret_0500": hh - 0.500 * span,
            "ret_0618": hh - 0.618 * span,
            "ret_0786": hh - 0.786 * span,
            "ext_1272": ll + 1.272 * span,
            "ext_1414": ll + 1.414 * span,
            "ext_1618": ll + 1.618 * span,
        }
    else:
        # Bearish: anchor = HH, completion = LL
        hh = leg.fib_0
        ll = leg.fib_100
        span = hh - ll
        return {
            "ret_0236": ll + 0.236 * span,  # shallow bounce back up
            "ret_0382": ll + 0.382 * span,
            "ret_0500": ll + 0.500 * span,
            "ret_0618": ll + 0.618 * span,
            "ret_0786": ll + 0.786 * span,
            "ext_1272": hh - 1.272 * span,  # extension further down
            "ext_1414": hh - 1.414 * span,
            "ext_1618": hh - 1.618 * span,
        }


# ---------------------------------------------------------------------------
# Per-leg measurement
# ---------------------------------------------------------------------------


def measure_leg_respect(
    leg: QualifiedLeg,
    daily_bars: dict,
    config: Fib3Config,
) -> FibRespectProfile:
    """
    Measure fib level visit and reaction rates for a single leg.

    Observation window: [discovery_bar, discovery_bar + fib_respect_window).
    """
    highs = daily_bars["highs"]
    lows = daily_bars["lows"]
    closes = daily_bars["closes"]
    n = daily_bars["n"]

    atr = leg.atr_at_detection
    db = leg.discovery_bar
    end = min(db + config.fib_respect_window, n)
    tol = atr * config.fib_visit_tol_atr
    react = atr * config.fib_react_min_atr

    levels = compute_standard_levels(leg)

    profile = FibRespectProfile(
        direction=leg.direction,
        discovery_bar=db,
        quality_score=leg.quality.total,
        quality_tier=leg.quality.tier,
    )

    is_retracement = lambda k: k.startswith("ret_")

    for key in FIB_LEVEL_KEYS:
        lvl_price = levels[key]
        lp = FibLevelProfile(level_key=key, level_price=lvl_price)
        min_prox = 99.0
        first_visit_bar = -1

        for bar in range(db, end):
            hi = highs[bar]
            lo = lows[bar]

            # Distance from bar range to level
            if lo <= lvl_price <= hi:
                dist_atr = 0.0
            else:
                dist_atr = min(abs(hi - lvl_price), abs(lo - lvl_price)) / atr if atr > 0 else 99.0

            if dist_atr < min_prox:
                min_prox = dist_atr

            if dist_atr <= config.fib_visit_tol_atr and not lp.visited:
                lp.visited = True
                lp.visit_bar = bar
                first_visit_bar = bar
                break  # Record first visit only

        lp.min_proximity_atr = round(min_prox, 3)

        # Reaction check: only if visited
        if lp.visited and first_visit_bar >= 0:
            look_end = min(first_visit_bar + config.fib_react_bars + 1, end)
            visit_close = closes[first_visit_bar]

            if is_retracement(key):
                # Retracement level: expect BOUNCE (bullish = close goes up; bearish = goes down)
                for fwd in range(first_visit_bar + 1, look_end):
                    if leg.direction == "bullish" and closes[fwd] >= visit_close + react:
                        lp.reacted = True
                        break
                    if leg.direction == "bearish" and closes[fwd] <= visit_close - react:
                        lp.reacted = True
                        break
            else:
                # Extension level: mark as reacted if price simply reached it
                lp.reacted = True

        profile.levels[key] = lp

    return profile


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def aggregate_by_tier(
    profiles: list[FibRespectProfile],
) -> dict[str, dict[str, dict]]:
    """
    Group profiles by quality tier (A/B/C/D) and compute per-level statistics.

    Returns:
      {
        "A": {"ret_0382": {"visit_rate": 0.8, "react_rate": 0.6, "n": 12}, ...},
        "B": {...},
        ...
        "ALL": {...},
      }
    """
    tiers: dict[str, list] = {"A": [], "B": [], "C": [], "D": [], "ALL": []}
    for p in profiles:
        tiers[p.quality_tier].append(p)
        tiers["ALL"].append(p)

    result: dict[str, dict] = {}
    for tier, tier_profiles in tiers.items():
        n = len(tier_profiles)
        if n == 0:
            result[tier] = {}
            continue
        tier_stats: dict[str, dict] = {}
        for key in FIB_LEVEL_KEYS:
            visited = sum(
                1 for p in tier_profiles if p.levels.get(key, FibLevelProfile(key, 0)).visited
            )
            reacted = sum(
                1 for p in tier_profiles if p.levels.get(key, FibLevelProfile(key, 0)).reacted
            )
            prox_vals = [
                p.levels[key].min_proximity_atr
                for p in tier_profiles
                if key in p.levels and p.levels[key].min_proximity_atr < 99.0
            ]
            avg_prox = sum(prox_vals) / len(prox_vals) if prox_vals else 99.0
            tier_stats[key] = {
                "visit_rate": visited / n,
                "react_rate": reacted / n,
                "avg_proximity_atr": round(avg_prox, 3),
                "n": n,
            }
        result[tier] = tier_stats

    return result
