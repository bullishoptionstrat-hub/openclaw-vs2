"""
Fib3 manipulation leg detector.

Detects QualifiedLeg objects with full quality scoring.
Captures prior_completion_price (the structural high/low BEFORE the anchor)
which is needed for CHoCH margin scoring.

Reuses fib2's pivot detection and ATR computation.
Applies looser displacement defaults (min 2.0 ATR) to capture all quality tiers.
"""

from __future__ import annotations

import numpy as np
from typing import Optional

from research.fib2.data import compute_atr
from research.fib2.detector import find_pivots
from research.fib3.model import Fib3Config, QualifiedLeg
from research.fib3 import quality_scorer as qs


# ---------------------------------------------------------------------------
# Fib level helpers (with fib3-exclusive 1.414 level)
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
        "fib_1414": ll + 1.414 * span,
        "fib_1618": ll + 1.618 * span,
        "stop_origin": max(ll - stop_buffer * atr, ll * 0.97),
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
        "fib_1414": hh - 1.414 * span,
        "fib_1618": hh - 1.618 * span,
        "stop_origin": min(hh + stop_buffer * atr, hh * 1.03),
        "stop_786": hh - (1.0 - 0.786) * span + stop_buffer * atr,
    }


# ---------------------------------------------------------------------------
# SPY regime helper
# ---------------------------------------------------------------------------


def _spy_bull_at_date(
    spy_closes: Optional[np.ndarray],
    spy_dates: Optional[list],
    target_date: str,
    sma_period: int = 200,
) -> bool:
    if spy_closes is None or spy_dates is None:
        return True
    idx = None
    for i in range(len(spy_dates) - 1, -1, -1):
        if spy_dates[i] <= target_date:
            idx = i
            break
    if idx is None or idx < sma_period - 1:
        return True
    start = max(0, idx - sma_period + 1)
    sma = float(np.mean(spy_closes[start : idx + 1]))
    return bool(spy_closes[idx] >= sma)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def find_qualified_legs(
    daily_bars: dict,
    config: Fib3Config,
    spy_daily: Optional[dict] = None,
) -> list[QualifiedLeg]:
    """
    Detect all manipulation legs, score each for quality, return QualifiedLeg list.

    Uses looser displacement defaults (config.min_displacement_atr, default 2.0)
    to capture all quality tiers for comparison.
    """
    highs = daily_bars["highs"]
    lows = daily_bars["lows"]
    closes = daily_bars["closes"]
    volumes = daily_bars["volumes"]
    dates = daily_bars["dates"]
    pn = config.pivot_n

    atr_arr = compute_atr(highs, lows, closes, config.atr_period)
    pivot_highs, pivot_lows = find_pivots(highs, lows, pn)

    spy_closes = spy_daily["closes"] if spy_daily else None
    spy_dates = spy_daily["dates"] if spy_daily else None

    legs: list[QualifiedLeg] = []

    if "bullish" in config.directions:
        legs.extend(
            _find_bullish(
                pivot_highs,
                pivot_lows,
                highs,
                lows,
                closes,
                volumes,
                dates,
                atr_arr,
                config,
                spy_closes,
                spy_dates,
                pn,
            )
        )
    if "bearish" in config.directions:
        legs.extend(
            _find_bearish(
                pivot_highs,
                pivot_lows,
                highs,
                lows,
                closes,
                volumes,
                dates,
                atr_arr,
                config,
                spy_closes,
                spy_dates,
                pn,
            )
        )

    legs = [l for l in legs if l.quality.total >= config.quality_min_score]
    if config.quality_min_sweep > 0:
        legs = [l for l in legs if l.quality.sweep_score >= config.quality_min_sweep]
    if config.quality_min_choch > 0:
        legs = [l for l in legs if l.quality.choch_score >= config.quality_min_choch]

    legs.sort(key=lambda l: l.discovery_bar)
    return legs


# ---------------------------------------------------------------------------
# Bullish legs
# ---------------------------------------------------------------------------


def _find_bullish(
    pivot_highs,
    pivot_lows,
    highs,
    lows,
    closes,
    volumes,
    dates,
    atr_arr,
    config: Fib3Config,
    spy_closes,
    spy_dates,
    pn,
) -> list[QualifiedLeg]:
    results = []

    for ll_idx in range(1, len(pivot_lows)):
        ll_bar, ll_price = pivot_lows[ll_idx]
        prior_ll_bar, prior_ll_price = pivot_lows[ll_idx - 1]

        # Must be a new lower low (sweep below prior LL)
        if ll_price >= prior_ll_price:
            continue

        # Sweep check
        if config.require_sweep:
            swept = False
            end = min(ll_bar + config.sweep_recovery_bars + 1, len(closes))
            for i in range(ll_bar, end):
                if closes[i] >= prior_ll_price:
                    swept = True
                    break
            if not swept:
                continue

        # Prior HH (for CHoCH scoring — need the HH before the LL)
        prior_hh_price: float | None = None
        for b, p in reversed(pivot_highs):
            if b < ll_bar:
                prior_hh_price = p
                break

        for hh_bar, hh_price in pivot_highs:
            if hh_bar <= ll_bar:
                continue

            span = hh_bar - ll_bar
            if span < config.min_leg_bars or span > config.max_leg_bars:
                continue

            # Completion must break prior HH (CHoCH requirement)
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

            if leg_pct < config.min_displacement_pct:
                break  # LL too small; no HH will fix it
            if leg_atr < config.min_displacement_atr:
                continue

            velocity = leg_points / max(span, 1) / atr
            if config.min_velocity_atr_per_bar > 0 and velocity < config.min_velocity_atr_per_bar:
                continue

            # Quality scoring
            disc_date = dates[discovery_bar] if discovery_bar < len(dates) else ""
            spy_bull = _spy_bull_at_date(spy_closes, spy_dates, disc_date)

            sw_s, sw_depth, sw_rec = qs.score_sweep(
                ll_bar, ll_price, prior_ll_price, "bullish", closes, atr, config
            )
            disp_s = qs.score_displacement(leg_atr, config)
            choch_s, choch_margin = qs.score_choch(hh_price, prior_hh_price, "bullish", atr, config)
            ctx_s, in_disc, vol_ratio = qs.score_context(
                discovery_bar,
                "bullish",
                highs,
                lows,
                closes,
                volumes,
                hh_bar,
                spy_bull,
                atr,
                config,
            )

            total = sw_s + disp_s + choch_s + ctx_s
            quality = _make_score(
                sw_s,
                disp_s,
                choch_s,
                ctx_s,
                total,
                sw_depth,
                sw_rec,
                leg_atr,
                choch_margin,
                in_disc,
                vol_ratio,
                spy_bull,
            )

            fib = _fib_levels_bullish(ll_price, hh_price, config.stop_buffer_atr, atr)

            results.append(
                QualifiedLeg(
                    direction="bullish",
                    anchor_bar=ll_bar,
                    anchor_price=ll_price,
                    completion_bar=hh_bar,
                    completion_price=hh_price,
                    discovery_bar=discovery_bar,
                    prior_pivot_price=prior_ll_price,
                    prior_completion_price=prior_hh_price if prior_hh_price else ll_price,
                    sweep_confirmed=config.require_sweep,
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
                    fib_1414=fib["fib_1414"],
                    fib_1618=fib["fib_1618"],
                    zone_low=fib["fib_382"],
                    zone_high=fib["fib_618"],
                    stop_price_origin=fib["stop_origin"],
                    stop_price_786=fib["stop_786"],
                    quality=quality,
                )
            )
            break  # One leg per LL anchor

    return results


# ---------------------------------------------------------------------------
# Bearish legs
# ---------------------------------------------------------------------------


def _find_bearish(
    pivot_highs,
    pivot_lows,
    highs,
    lows,
    closes,
    volumes,
    dates,
    atr_arr,
    config: Fib3Config,
    spy_closes,
    spy_dates,
    pn,
) -> list[QualifiedLeg]:
    results = []

    for hh_idx in range(1, len(pivot_highs)):
        hh_bar, hh_price = pivot_highs[hh_idx]
        prior_hh_bar, prior_hh_price = pivot_highs[hh_idx - 1]

        if hh_price <= prior_hh_price:
            continue

        if config.require_sweep:
            swept = False
            end = min(hh_bar + config.sweep_recovery_bars + 1, len(closes))
            for i in range(hh_bar, end):
                if closes[i] <= prior_hh_price:
                    swept = True
                    break
            if not swept:
                continue

        prior_ll_price: float | None = None
        for b, p in reversed(pivot_lows):
            if b < hh_bar:
                prior_ll_price = p
                break

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

            disc_date = dates[discovery_bar] if discovery_bar < len(dates) else ""
            spy_bull = _spy_bull_at_date(spy_closes, spy_dates, disc_date)

            sw_s, sw_depth, sw_rec = qs.score_sweep(
                hh_bar, hh_price, prior_hh_price, "bearish", closes, atr, config
            )
            disp_s = qs.score_displacement(leg_atr, config)
            choch_s, choch_margin = qs.score_choch(ll_price, prior_ll_price, "bearish", atr, config)
            ctx_s, in_disc, vol_ratio = qs.score_context(
                discovery_bar,
                "bearish",
                highs,
                lows,
                closes,
                volumes,
                ll_bar,
                spy_bull,
                atr,
                config,
            )

            total = sw_s + disp_s + choch_s + ctx_s
            quality = _make_score(
                sw_s,
                disp_s,
                choch_s,
                ctx_s,
                total,
                sw_depth,
                sw_rec,
                leg_atr,
                choch_margin,
                in_disc,
                vol_ratio,
                spy_bull,
            )

            fib = _fib_levels_bearish(hh_price, ll_price, config.stop_buffer_atr, atr)

            results.append(
                QualifiedLeg(
                    direction="bearish",
                    anchor_bar=hh_bar,
                    anchor_price=hh_price,
                    completion_bar=ll_bar,
                    completion_price=ll_price,
                    discovery_bar=discovery_bar,
                    prior_pivot_price=prior_hh_price,
                    prior_completion_price=prior_ll_price if prior_ll_price else hh_price,
                    sweep_confirmed=config.require_sweep,
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
                    fib_1414=fib["fib_1414"],
                    fib_1618=fib["fib_1618"],
                    zone_low=fib["fib_618"],
                    zone_high=fib["fib_382"],
                    stop_price_origin=fib["stop_origin"],
                    stop_price_786=fib["stop_786"],
                    quality=quality,
                )
            )
            break

    return results


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_score(
    sw_s,
    disp_s,
    choch_s,
    ctx_s,
    total,
    sw_depth,
    sw_rec,
    leg_atr,
    choch_margin,
    in_disc,
    vol_ratio,
    spy_bull,
) -> "LegQualityScore":  # noqa: F821
    from research.fib3.model import LegQualityScore

    return LegQualityScore(
        sweep_score=round(sw_s, 2),
        displacement_score=round(disp_s, 2),
        choch_score=round(choch_s, 2),
        context_score=round(ctx_s, 2),
        total=round(total, 2),
        sweep_depth_atr=round(sw_depth, 3),
        sweep_recovery_bars=sw_rec,
        displacement_atr=round(leg_atr, 3),
        choch_margin_atr=round(choch_margin, 3),
        in_discount=in_disc,
        volume_ratio=round(vol_ratio, 3),
        spy_bull=spy_bull,
    )
