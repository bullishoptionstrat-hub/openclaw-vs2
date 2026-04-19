"""
fib4 entry decision engine.

The core of fib4: given a QualifiedLeg and price data, decide whether
and when to enter based on the configured trigger type.

Entry state machine
-------------------
  decide_entry()   — top-level dispatcher; routes to 1H or daily path
  find_entry_daily()  — daily-bar scan with zone-touch tracking
  find_entry_1h()     — 1H-bar scan mapping back to daily bar for trade mgmt
  _effective_zone()   — compute eff_low/eff_high/midzone from trigger type

Trigger definitions
-------------------
  touch_rejection     wick into zone, same-bar close above/below midzone
  nextbar_confirm     zone touched bar B, bar B+1 confirms directional move
  close_in_zone       close inside zone (fib3 baseline behavior)
  midzone_only        tight band around fib_50 + rejection check
  zone_0382_only      tight band around fib_382 + rejection check
  zone_0618_only      tight band around fib_618 + rejection check
  1h_rejection        1H wick into zone, 1H close above/below midzone
  1h_structure_shift  1H local pivot inside zone
  1h_displacement_off 1H close beyond zone edge after entering zone

All triggers respect:
  - invalidation: stop_price_origin breached before entry
  - no_passive_max_bars: skip if drifting in zone too long (if enabled)
"""

from __future__ import annotations

import dataclasses
import numpy as np
from typing import Optional

from research.fib4.model import EntryDecision, Fib4Config


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------


def decide_entry(
    leg,
    daily_bars: dict,
    atr_arr: np.ndarray,
    config: Fib4Config,
    hourly_bars: Optional[dict] = None,
    date_to_1h: Optional[dict] = None,
) -> EntryDecision:
    """
    Route to 1H or daily entry scan based on config.entry_trigger.

    When a 1H trigger is requested but hourly data is unavailable,
    falls back to config.fallback_trigger on daily bars.
    """
    trigger = config.entry_trigger

    if trigger.startswith("1h_"):
        if hourly_bars is not None and date_to_1h is not None:
            return find_entry_1h(leg, daily_bars, hourly_bars, date_to_1h, config)
        else:
            # Fall back to daily using fallback_trigger
            fb_config = dataclasses.replace(config, entry_trigger=config.fallback_trigger)
            decision = find_entry_daily(leg, daily_bars, atr_arr, fb_config)
            if decision.enter:
                # Mark that this was a fallback
                return dataclasses.replace(decision, trigger_type=trigger + "_daily_fallback")
            return decision

    return find_entry_daily(leg, daily_bars, atr_arr, config)


# ---------------------------------------------------------------------------
# Daily scan
# ---------------------------------------------------------------------------


def find_entry_daily(
    leg,
    daily_bars: dict,
    atr_arr: np.ndarray,
    config: Fib4Config,
) -> EntryDecision:
    """
    Scan daily bars from discovery_bar, apply entry trigger, return decision.

    Tracks zone-touch state for nextbar_confirm and no_passive logic.
    """
    direction = leg.direction
    opens = daily_bars["opens"]
    highs = daily_bars["highs"]
    lows = daily_bars["lows"]
    closes = daily_bars["closes"]
    n = daily_bars["n"]
    trigger = config.entry_trigger

    start_bar = leg.discovery_bar
    if start_bar >= n - 1:
        return EntryDecision(skipped=True, skip_reason="no_trigger_fired")

    # ATR at discovery bar (for zone width calculations)
    atr = _get_atr(atr_arr, start_bar, leg.atr_at_detection)
    eff_low, eff_high, midzone = _effective_zone(leg, trigger, atr, config)

    zone_deadline = min(start_bar + config.max_zone_wait_bars, n - 2)

    zone_first_touch_bar: Optional[int] = None
    passive_in_zone = 0

    for bar in range(start_bar, zone_deadline + 1):
        lo = lows[bar]
        hi = highs[bar]
        c = closes[bar]

        # Invalidation: stop broken before entry
        if direction == "bullish" and lo <= leg.stop_price_origin:
            return EntryDecision(skipped=True, skip_reason="invalidated")
        if direction == "bearish" and hi >= leg.stop_price_origin:
            return EntryDecision(skipped=True, skip_reason="invalidated")

        # Zone overlap: any part of the bar enters the zone
        in_zone = (direction == "bullish" and lo <= eff_high) or (
            direction == "bearish" and hi >= eff_low
        )

        if in_zone:
            if zone_first_touch_bar is None:
                zone_first_touch_bar = bar
            passive_in_zone += 1

            # No-passive timeout
            if config.no_passive_max_bars > 0 and passive_in_zone > config.no_passive_max_bars:
                return EntryDecision(skipped=True, skip_reason="passive_timeout")

        # ── Trigger logic ────────────────────────────────────────────────

        if trigger in (
            "touch_rejection",
            "midzone_only",
            "zone_0382_only",
            "zone_0618_only",
        ):
            if in_zone:
                triggered = (direction == "bullish" and lo <= eff_high and c >= midzone) or (
                    direction == "bearish" and hi >= eff_low and c <= midzone
                )
                if triggered and bar + 1 <= zone_deadline:
                    return EntryDecision(
                        enter=True,
                        entry_bar_daily=bar + 1,
                        entry_price=opens[bar + 1],
                        trigger_type=trigger,
                    )

        elif trigger == "close_in_zone":
            if in_zone and eff_low <= c <= eff_high and bar + 1 <= zone_deadline:
                return EntryDecision(
                    enter=True,
                    entry_bar_daily=bar + 1,
                    entry_price=opens[bar + 1],
                    trigger_type=trigger,
                )

        elif trigger == "nextbar_confirm":
            if zone_first_touch_bar is not None and bar == zone_first_touch_bar + 1:
                bar_atr = _get_atr(atr_arr, bar, leg.atr_at_detection)
                prev_c = closes[zone_first_touch_bar]
                threshold = config.nextbar_confirm_atr * bar_atr
                confirmed = (direction == "bullish" and c >= prev_c + threshold) or (
                    direction == "bearish" and c <= prev_c - threshold
                )
                if confirmed and bar + 1 <= zone_deadline:
                    return EntryDecision(
                        enter=True,
                        entry_bar_daily=bar + 1,
                        entry_price=opens[bar + 1],
                        trigger_type=trigger,
                    )
                else:
                    # One chance only: first touch + next bar
                    return EntryDecision(skipped=True, skip_reason="nextbar_confirm_failed")

        elif trigger == "displacement_off":
            if in_zone:
                triggered = (direction == "bullish" and lo <= eff_high and c >= eff_high) or (
                    direction == "bearish" and hi >= eff_low and c <= eff_low
                )
                if triggered and bar + 1 <= zone_deadline:
                    return EntryDecision(
                        enter=True,
                        entry_bar_daily=bar + 1,
                        entry_price=opens[bar + 1],
                        trigger_type=trigger,
                    )

    return EntryDecision(skipped=True, skip_reason="no_trigger_fired")


# ---------------------------------------------------------------------------
# 1H scan
# ---------------------------------------------------------------------------


def find_entry_1h(
    leg,
    daily_bars: dict,
    hourly_bars: dict,
    date_to_1h: dict,
    config: Fib4Config,
) -> EntryDecision:
    """
    Scan 1H bars from leg discovery date, apply 1H trigger.
    Returns EntryDecision with entry_bar_daily mapped to closest daily bar.

    Trade management always runs on daily bars; only the entry price is
    sourced from the 1H bar open.
    """
    trigger = config.entry_trigger  # "1h_rejection" | "1h_structure_shift" | ...
    direction = leg.direction

    d_dates = daily_bars["dates"]
    start_bar = leg.discovery_bar
    n_daily = daily_bars["n"]

    # Find hourly start index at or after discovery date
    disc_date = d_dates[start_bar] if start_bar < len(d_dates) else None
    if disc_date is None:
        return EntryDecision(skipped=True, skip_reason="no_1h_data")

    h_start = None
    for d in d_dates[start_bar:]:
        if d in date_to_1h:
            h_start, _ = date_to_1h[d]
            break
    if h_start is None:
        return EntryDecision(skipped=True, skip_reason="no_1h_data")

    h_highs = hourly_bars["highs"]
    h_lows = hourly_bars["lows"]
    h_closes = hourly_bars["closes"]
    h_opens = hourly_bars["opens"]
    h_dates = hourly_bars["dates"]
    h_n = hourly_bars["n"]

    eff_low = leg.zone_low
    eff_high = leg.zone_high
    midzone = (eff_low + eff_high) / 2.0
    pn = config.entry_pivot_n

    # Scan window: max_zone_wait_bars * 7 hourly bars (~7 trading hours/day)
    h_deadline = min(h_start + config.max_zone_wait_bars * 7, h_n - 1)

    for hb in range(h_start, h_deadline):
        lo = h_lows[hb]
        hi = h_highs[hb]
        c = h_closes[hb]

        # Stop invalidation
        if direction == "bullish" and lo <= leg.stop_price_origin:
            return EntryDecision(skipped=True, skip_reason="invalidated")
        if direction == "bearish" and hi >= leg.stop_price_origin:
            return EntryDecision(skipped=True, skip_reason="invalidated")

        in_zone = (direction == "bullish" and lo <= eff_high) or (
            direction == "bearish" and hi >= eff_low
        )
        if not in_zone:
            continue

        triggered = False

        if trigger == "1h_rejection":
            triggered = (direction == "bullish" and lo <= eff_high and c >= midzone) or (
                direction == "bearish" and hi >= eff_low and c <= midzone
            )

        elif trigger == "1h_structure_shift":
            if hb >= pn and hb + pn < h_n:
                if direction == "bullish":
                    window = h_lows[hb - pn : hb + pn + 1]
                    is_pivot = h_lows[hb] == np.min(window)
                    in_zone_pivot = eff_low <= h_lows[hb] <= eff_high
                    triggered = is_pivot and in_zone_pivot
                else:
                    window = h_highs[hb - pn : hb + pn + 1]
                    is_pivot = h_highs[hb] == np.max(window)
                    in_zone_pivot = eff_low <= h_highs[hb] <= eff_high
                    triggered = is_pivot and in_zone_pivot

        elif trigger == "1h_displacement_off":
            triggered = (direction == "bullish" and lo <= eff_high and c >= eff_high) or (
                direction == "bearish" and hi >= eff_low and c <= eff_low
            )

        if triggered and hb + 1 < h_n:
            entry_h_bar = hb + 1
            entry_price = h_opens[entry_h_bar]
            entry_date = h_dates[entry_h_bar]

            # Map hourly entry date back to daily bar index
            entry_daily_bar = _date_to_daily_bar(entry_date, d_dates, start_bar, n_daily)
            if entry_daily_bar is None:
                return EntryDecision(skipped=True, skip_reason="no_trigger_fired")

            return EntryDecision(
                enter=True,
                entry_bar_daily=entry_daily_bar,
                entry_price=entry_price,
                trigger_type=trigger,
            )

    return EntryDecision(skipped=True, skip_reason="no_trigger_fired")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _effective_zone(
    leg,
    trigger: str,
    atr: float,
    config: Fib4Config,
) -> tuple[float, float, float]:
    """Return (eff_low, eff_high, midzone) for the given trigger type."""
    half = max(config.midzone_tolerance_atr * atr, 0.005)

    if trigger == "midzone_only":
        center = leg.fib_50
        return center - half, center + half, center

    if trigger == "zone_0382_only":
        center = leg.fib_382
        return center - half, center + half, center

    if trigger == "zone_0618_only":
        center = leg.fib_618
        return center - half, center + half, center

    # Default: full zone
    mid = (leg.zone_low + leg.zone_high) / 2.0
    return leg.zone_low, leg.zone_high, mid


def _get_atr(atr_arr: np.ndarray, bar: int, fallback: float) -> float:
    """Return ATR at bar, falling back to leg's ATR if NaN or out of range."""
    if bar < len(atr_arr) and not np.isnan(atr_arr[bar]) and atr_arr[bar] > 0:
        return float(atr_arr[bar])
    return fallback


def _date_to_daily_bar(
    target_date: str,
    d_dates: list,
    start_from: int,
    n: int,
) -> Optional[int]:
    """
    Find daily bar index for target_date.
    target_date may be "YYYYMMDD" or "YYYYMMDD HH:MM" — we use date prefix.
    Returns the first daily bar whose date >= target_date[0:8].
    """
    d = target_date[:8]
    for i in range(start_from, n):
        if d_dates[i] >= d:
            return i
    return None
