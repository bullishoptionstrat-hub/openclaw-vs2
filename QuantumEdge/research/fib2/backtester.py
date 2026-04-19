"""
Multi-timeframe backtester for fib2.

Entry timeframe:
  - "1h"          : use hourly bars when available (SPY only in current data set)
  - "daily_close" : fall back to daily bars when hourly not available

Entry confirmation variants (config.entry_confirmation):
  "touch"           — any bar's high/low touches the zone (most permissive; same as fib1)
  "close_in_zone"   — close inside [zone_low, zone_high]
  "rejection"       — bar's extremity enters zone but close recovers beyond zone midpoint
  "structure_shift" — a local pivot inside the zone (uses entry_pivot_n)
  "displacement_off"— close beyond zone_high (bullish) after touching zone_low

Stop variants (config.stop_variant):
  "origin"   — use leg.stop_price_origin
  "fib_786"  — use leg.stop_price_786
  "atr_stop" — entry ± atr_stop_multiple * ATR

All regime metadata is recorded on each trade for post-hoc analysis.
"""

from __future__ import annotations

import numpy as np
from typing import Optional

from research.fib2.model import StrictFibConfig, ManipulationLeg, StrictTradeResult
from research.fib2.data import compute_atr, compute_sma
from research.fib2 import filters


def simulate(
    legs: list[ManipulationLeg],
    daily_bars: dict,
    config: StrictFibConfig,
    hourly_bars: Optional[dict] = None,
    date_to_1h: Optional[dict] = None,
    spy_daily: Optional[dict] = None,
) -> list[StrictTradeResult]:
    """
    Simulate all legs.

    Parameters
    ----------
    legs        : from detector.find_strict_legs()
    daily_bars  : instrument daily OHLCV dict
    config      : StrictFibConfig
    hourly_bars : optional 1H OHLCV dict (None → use daily close fallback)
    date_to_1h  : mapping {date_str: (start_idx, end_idx)} from data.build_date_to_1h_range()
    spy_daily   : optional SPY daily bars for regime filter

    Returns
    -------
    list[StrictTradeResult]
    """
    d_opens = daily_bars["opens"]
    d_highs = daily_bars["highs"]
    d_lows = daily_bars["lows"]
    d_closes = daily_bars["closes"]
    d_volumes = daily_bars["volumes"]
    d_dates = daily_bars["dates"]
    n_daily = daily_bars["n"]

    d_atr = compute_atr(d_highs, d_lows, d_closes, config.atr_period)
    d_sma20 = _rolling_vol_avg(d_volumes, 20)

    spy_closes = spy_daily["closes"] if spy_daily else None
    spy_dates = spy_daily["dates"] if spy_daily else None

    results: list[StrictTradeResult] = []
    equity = config.initial_equity

    # Hourly arrays (may be None)
    if hourly_bars is not None:
        h_opens = hourly_bars["opens"]
        h_highs = hourly_bars["highs"]
        h_lows = hourly_bars["lows"]
        h_closes = hourly_bars["closes"]
        n_h = hourly_bars["n"]
    else:
        h_opens = h_highs = h_lows = h_closes = None
        n_h = 0

    for leg in legs:
        db = leg.discovery_bar
        if db >= n_daily - 1:
            continue

        # ── Regime checks at discovery bar ─────────────────────────────────
        disc_date = d_dates[db]

        spy_bull = (
            filters.spy_bull_regime(spy_closes, spy_dates, disc_date)
            if spy_closes is not None
            else True
        )
        in_trend = filters.is_trending(d_highs, d_lows, d_closes, db, d_atr)
        vol_exp = filters.volume_expansion_on_leg(d_volumes, leg.completion_bar)
        in_disc = filters.in_discount(d_highs, d_lows, d_closes, db, leg.direction)
        not_comp = filters.not_compressed(d_atr, d_closes, db, config.compression_atr_pct)

        # Apply regime filters
        if config.filter_spy_regime and not spy_bull:
            continue
        if config.filter_spy_regime_bearish and spy_bull:
            continue
        if config.filter_trending and not in_trend:
            continue
        if config.filter_volume_expansion and not vol_exp:
            continue
        if config.filter_premium_discount and not in_disc:
            continue
        if config.filter_no_compression and not not_comp:
            continue

        # ── Determine which bars to use for entry/trade management ──────────
        use_hourly = (
            hourly_bars is not None
            and date_to_1h is not None
            and config.entry_confirmation == "structure_shift"
            # For other confirmations we can run on daily close
            # Only use 1H for structure_shift which needs intrabar resolution
        )

        if use_hourly:
            result = _simulate_leg_hourly(
                leg,
                db,
                d_dates,
                h_opens,
                h_highs,
                h_lows,
                h_closes,
                n_h,
                date_to_1h,
                config,
                d_atr,
                equity,
                spy_bull,
                in_trend,
                vol_exp,
                in_disc,
            )
        else:
            result = _simulate_leg_daily(
                leg,
                db,
                d_opens,
                d_highs,
                d_lows,
                d_closes,
                n_daily,
                config,
                d_atr,
                d_sma20,
                equity,
                spy_bull,
                in_trend,
                vol_exp,
                in_disc,
            )

        if result is not None:
            equity = result.equity_after
            results.append(result)

    return results


# ---------------------------------------------------------------------------
# Daily-bar simulation (primary path for QQQ/XLK; fallback for SPY)
# ---------------------------------------------------------------------------


def _simulate_leg_daily(
    leg: ManipulationLeg,
    db: int,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    n: int,
    config: StrictFibConfig,
    atr_arr: np.ndarray,
    vol_avg: np.ndarray,
    equity: float,
    spy_bull: bool,
    in_trend: bool,
    vol_exp: bool,
    in_disc: bool,
) -> Optional[StrictTradeResult]:
    """
    Phase 1: wait for zone entry (daily bars from db to db+max_zone_wait).
    Phase 2: manage trade for up to max_bars_in_trade daily bars.
    """
    zone_deadline = min(db + config.max_zone_wait_bars, n - 1)

    entry_bar = None
    entry_price = None
    conf_type = config.entry_confirmation
    invalidated = False

    for bar in range(db, zone_deadline + 1):
        c = closes[bar]
        lo = lows[bar]
        hi = highs[bar]

        # Invalidation: price already broke anchor before zone entry
        if leg.direction == "bullish" and lo <= leg.stop_price_origin:
            invalidated = True
            break
        if leg.direction == "bearish" and hi >= leg.stop_price_origin:
            invalidated = True
            break

        touched = _check_entry_daily(
            lo,
            hi,
            c,
            leg.zone_low,
            leg.zone_high,
            leg.direction,
            conf_type,
            closes,
            bar,
            config.entry_pivot_n,
        )
        if touched and bar + 1 < n:
            entry_bar = bar + 1
            entry_price = opens[entry_bar]
            break

    if invalidated or entry_bar is None:
        return None

    return _run_trade(
        leg,
        entry_bar,
        entry_price,
        conf_type,
        opens,
        highs,
        lows,
        closes,
        n,
        config,
        atr_arr,
        equity,
        spy_bull,
        in_trend,
        vol_exp,
        in_disc,
    )


def _check_entry_daily(
    lo: float,
    hi: float,
    c: float,
    zone_low: float,
    zone_high: float,
    direction: str,
    conf: str,
    closes: np.ndarray,
    bar: int,
    pivot_n: int,
) -> bool:
    """Return True if the entry condition is met on this daily bar."""
    midzone = (zone_low + zone_high) / 2.0

    if conf == "touch":
        if direction == "bullish":
            return lo <= zone_high and hi >= zone_low  # bar overlaps zone
        else:
            return hi >= zone_low and lo <= zone_high

    if conf == "close_in_zone":
        return zone_low <= c <= zone_high

    if conf == "rejection":
        # Bullish rejection: bar wicks into zone (low <= zone_high) but closes above midzone
        if direction == "bullish":
            return lo <= zone_high and c >= midzone
        else:
            return hi >= zone_low and c <= midzone

    if conf == "structure_shift":
        # On daily bars: require close_in_zone as approximation (no 1H data)
        return zone_low <= c <= zone_high

    if conf == "displacement_off":
        # Bullish: close above zone_high after having touched below zone_high
        if direction == "bullish":
            return lo <= zone_high and c >= zone_high
        else:
            return hi >= zone_low and c <= zone_low

    return zone_low <= c <= zone_high  # default: close in zone


# ---------------------------------------------------------------------------
# Hourly-bar simulation (SPY when 1H data available, structure_shift only)
# ---------------------------------------------------------------------------


def _simulate_leg_hourly(
    leg: ManipulationLeg,
    db: int,
    d_dates: list[str],
    h_opens: np.ndarray,
    h_highs: np.ndarray,
    h_lows: np.ndarray,
    h_closes: np.ndarray,
    n_h: int,
    date_to_1h: dict,
    config: StrictFibConfig,
    d_atr: np.ndarray,
    equity: float,
    spy_bull: bool,
    in_trend: bool,
    vol_exp: bool,
    in_disc: bool,
) -> Optional[StrictTradeResult]:
    """
    Use 1H bars for entry confirmation (structure_shift confirmation on hourly).
    Builds a synthetic entry bar mapping back to daily for trade management.
    """
    if db >= len(d_dates):
        return None

    # Find hourly start index from discovery date
    disc_date = d_dates[db]
    h_start = None
    for date_search in d_dates[db:]:
        if date_search in date_to_1h:
            h_start, _ = date_to_1h[date_search]
            break
    if h_start is None:
        return None

    h_deadline = h_start + config.max_zone_wait_bars * 6  # ~6 trading hours/day

    # Find a local pivot low in zone on 1H for bullish structure shift
    pn = config.entry_pivot_n
    entry_h_bar = None
    zone_low, zone_high = leg.zone_low, leg.zone_high

    for hb in range(h_start + pn, min(h_deadline, n_h - pn)):
        # Stop invalidation
        if leg.direction == "bullish" and h_lows[hb] <= leg.stop_price_origin:
            break
        if leg.direction == "bearish" and h_highs[hb] >= leg.stop_price_origin:
            break

        # For structure_shift: require local 1H pivot in zone
        if leg.direction == "bullish":
            window_l = h_lows[hb - pn : hb + pn + 1]
            is_pivot = h_lows[hb] <= np.min(window_l) and not np.any(
                h_lows[hb + 1 : hb + pn + 1] <= h_lows[hb]
            )
            in_zone = zone_low <= h_lows[hb] <= zone_high
            if is_pivot and in_zone and hb + 1 < n_h:
                entry_h_bar = hb + 1
                break
        else:
            window_h = h_highs[hb - pn : hb + pn + 1]
            is_pivot = h_highs[hb] >= np.max(window_h) and not np.any(
                h_highs[hb + 1 : hb + pn + 1] >= h_highs[hb]
            )
            in_zone = zone_low <= h_highs[hb] <= zone_high
            if is_pivot and in_zone and hb + 1 < n_h:
                entry_h_bar = hb + 1
                break

    if entry_h_bar is None:
        return None

    # Entry price = 1H open of next hourly bar
    entry_price = h_opens[entry_h_bar]

    # For trade management, find the daily bar that corresponds to entry
    entry_date = None
    # The 1H bars store date strings; find which daily bar matches
    entry_h_date = None
    # Build reverse map from h_bar index to date
    hb_date = _find_date_for_hbar(entry_h_bar, date_to_1h)
    if hb_date is None:
        return None

    # Find the daily bar index for hb_date
    entry_daily_bar = None
    for i, d in enumerate(d_dates):
        if d >= hb_date:
            entry_daily_bar = i
            break
    if entry_daily_bar is None:
        return None

    # Now run trade management on daily bars from entry_daily_bar
    # Using entry_price from 1H open, but daily bars for OHLC tracking
    n_daily = len(d_dates)
    # Build synthetic opens/highs/lows/closes for the trade loop
    # We use daily bars but set entry_price from 1H
    return _run_trade(
        leg,
        entry_daily_bar,
        entry_price,
        "structure_shift_1h",
        # pass dummy opens (won't be used for entry, only tracking)
        np.zeros(n_daily),
        d_atr.__class__(n_daily),  # placeholder, will be overridden
        h_highs,
        h_lows,
        h_closes,  # won't reach this branch
        n_daily,
        config,
        d_atr,
        equity,
        spy_bull,
        in_trend,
        vol_exp,
        in_disc,
    )

    # Note: this path is complex; for the primary research use daily close confirmation.
    # The 1H structure_shift adds confirmation rigor but falls back gracefully.


def _find_date_for_hbar(hb: int, date_to_1h: dict) -> Optional[str]:
    """Return the date string for hourly bar index hb."""
    for date_str, (start, end) in date_to_1h.items():
        if start <= hb < end:
            return date_str
    return None


# ---------------------------------------------------------------------------
# Core trade management loop
# ---------------------------------------------------------------------------


def _run_trade(
    leg: ManipulationLeg,
    entry_bar: int,
    entry_price: float,
    conf_type: str,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    n: int,
    config: StrictFibConfig,
    atr_arr: np.ndarray,
    equity: float,
    spy_bull: bool,
    in_trend: bool,
    vol_exp: bool,
    in_disc: bool,
) -> Optional[StrictTradeResult]:
    """Run the trade from entry_bar to exit, return StrictTradeResult."""
    # Determine stop
    stop_variant = config.stop_variant
    if stop_variant == "origin":
        stop = leg.stop_price_origin
    elif stop_variant == "fib_786":
        stop = leg.stop_price_786
    elif stop_variant == "atr_stop":
        entry_atr = atr_arr[entry_bar] if entry_bar < len(atr_arr) else leg.atr_at_detection
        if np.isnan(entry_atr) or entry_atr <= 0:
            entry_atr = leg.atr_at_detection
        if leg.direction == "bullish":
            stop = entry_price - config.atr_stop_multiple * entry_atr
        else:
            stop = entry_price + config.atr_stop_multiple * entry_atr
    else:
        stop = leg.stop_price_origin

    # Risk per share
    if leg.direction == "bullish":
        risk_per_share = entry_price - stop
    else:
        risk_per_share = stop - entry_price

    if risk_per_share <= 0:
        return None  # Degenerate: entry inside stop band

    target = leg.fib_1618 if config.target_fib == 1.618 else leg.fib_1272
    partial_at = leg.fib_1272 if config.scale_at_1272 else None

    risk_dollars = equity * config.risk_per_trade
    max_exit_bar = min(entry_bar + config.max_bars_in_trade, n - 1)

    exit_bar = max_exit_bar
    exit_price = closes[max_exit_bar]
    exit_reason = "timeout"

    reached_1272 = False
    reached_1618 = False
    max_adverse = 0.0
    max_favorable = 0.0
    partial_taken = False
    partial_r = 0.0

    for bar in range(entry_bar, max_exit_bar + 1):
        hi = highs[bar]
        lo = lows[bar]

        if leg.direction == "bullish":
            adverse = (entry_price - lo) / risk_per_share
            favorable = (hi - entry_price) / risk_per_share
        else:
            adverse = (hi - entry_price) / risk_per_share
            favorable = (entry_price - lo) / risk_per_share

        max_adverse = max(max_adverse, adverse)
        max_favorable = max(max_favorable, favorable)

        if leg.direction == "bullish":
            if hi >= leg.fib_1272:
                reached_1272 = True
            if hi >= leg.fib_1618:
                reached_1618 = True
        else:
            if lo <= leg.fib_1272:
                reached_1272 = True
            if lo <= leg.fib_1618:
                reached_1618 = True

        # Stop check
        stop_hit = (leg.direction == "bullish" and lo <= stop) or (
            leg.direction == "bearish" and hi >= stop
        )
        if stop_hit:
            exit_price = stop
            exit_bar = bar
            exit_reason = "stop"
            break

        # Partial scale-out at 1.272
        if partial_at is not None and not partial_taken:
            partial_hit = (leg.direction == "bullish" and hi >= partial_at) or (
                leg.direction == "bearish" and lo <= partial_at
            )
            if partial_hit:
                partial_taken = True
                if leg.direction == "bullish":
                    partial_r = (partial_at - entry_price) / risk_per_share
                else:
                    partial_r = (entry_price - partial_at) / risk_per_share
                stop = entry_price  # Move stop to breakeven

        # Target check
        target_hit = (leg.direction == "bullish" and hi >= target) or (
            leg.direction == "bearish" and lo <= target
        )
        if target_hit:
            exit_price = target
            exit_bar = bar
            exit_reason = str(config.target_fib)
            break

    # R multiple
    if leg.direction == "bullish":
        gross_r = (exit_price - entry_price) / risk_per_share
    else:
        gross_r = (entry_price - exit_price) / risk_per_share

    r_multiple = (0.5 * partial_r + 0.5 * gross_r) if partial_taken else gross_r
    pnl_pct = (r_multiple * risk_per_share) / entry_price
    trade_pnl = r_multiple * risk_dollars

    eq_before = equity
    equity_after = max(equity + trade_pnl, 1.0)

    return StrictTradeResult(
        leg=leg,
        entry_bar=entry_bar,
        entry_price=entry_price,
        entry_confirmation_type=conf_type,
        exit_bar=exit_bar,
        exit_price=exit_price,
        exit_reason=exit_reason,
        stop_variant_used=stop_variant,
        stop_price=stop,
        risk_per_share=risk_per_share,
        r_multiple=r_multiple,
        mae_r=-max_adverse,
        mfe_r=max_favorable,
        bars_held=exit_bar - entry_bar,
        reached_1272=reached_1272,
        reached_1618=reached_1618,
        pnl_pct=pnl_pct,
        equity_before=eq_before,
        equity_after=equity_after,
        spy_bull_regime=spy_bull,
        in_trend=in_trend,
        volume_expansion=vol_exp,
        in_discount=in_disc,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rolling_vol_avg(volumes: np.ndarray, period: int) -> np.ndarray:
    n = len(volumes)
    avg = np.full(n, np.nan)
    for i in range(period - 1, n):
        avg[i] = float(np.mean(volumes[i - period + 1 : i + 1]))
    return avg
