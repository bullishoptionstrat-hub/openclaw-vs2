"""
fib6 execution engine.

Extends fib4's execution with:
  1h_reclaim_after_sweep -- new 1H trigger for fib6

For all other triggers, delegates to fib4's decide_entry().

Trigger: 1h_reclaim_after_sweep
  For bullish: after leg discovery, scan 1H bars for:
    1. A sweep: 1H bar where lo < zone_low
    2. A reclaim: first 1H bar AFTER sweep where close >= zone_low
    Entry: next 1H open after the reclaim bar.
  This isolates the "failed sweep / liquidity sweep" entry pattern.
  If no hourly data, falls back to fallback_trigger on daily bars.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

import numpy as np

from research.fib4.model import EntryDecision, Fib4Config
from research.fib4 import execution as _fib4_exec


# ---------------------------------------------------------------------------
# Top-level dispatcher (extends fib4's dispatcher)
# ---------------------------------------------------------------------------


def decide_entry(
    leg,
    daily_bars: dict,
    atr_arr: np.ndarray,
    config,
    hourly_bars: Optional[dict] = None,
    date_to_1h: Optional[dict] = None,
) -> EntryDecision:
    """
    Route entry decision.

    Handles 1h_reclaim_after_sweep as a new trigger.
    All other triggers are delegated to fib4's decide_entry().
    """
    trigger = config.entry_trigger

    if trigger == "1h_reclaim_after_sweep":
        if hourly_bars is not None and date_to_1h is not None:
            return _find_entry_1h_reclaim(leg, daily_bars, hourly_bars, date_to_1h, config)
        else:
            # Daily fallback
            fb_config = dataclasses.replace(config, entry_trigger=config.fallback_trigger)
            decision = _fib4_exec.find_entry_daily(leg, daily_bars, atr_arr, fb_config)
            if decision.enter:
                return dataclasses.replace(
                    decision, trigger_type="1h_reclaim_after_sweep_daily_fallback"
                )
            return decision

    # All other triggers: delegate to fib4
    return _fib4_exec.decide_entry(
        leg,
        daily_bars,
        atr_arr,
        config,
        hourly_bars=hourly_bars,
        date_to_1h=date_to_1h,
    )


# ---------------------------------------------------------------------------
# 1H reclaim after sweep trigger
# ---------------------------------------------------------------------------


def _find_entry_1h_reclaim(
    leg,
    daily_bars: dict,
    hourly_bars: dict,
    date_to_1h: dict,
    config,
) -> EntryDecision:
    """
    1H reclaim-after-sweep entry.

    For bullish:
      Phase 1: find first 1H bar where lo < zone_low (the sweep)
      Phase 2: find first 1H bar AFTER sweep where close >= zone_low (reclaim)
      Entry: open of the 1H bar after reclaim

    For bearish:
      Phase 1: first 1H bar where hi > zone_high (the sweep)
      Phase 2: first 1H bar after sweep where close <= zone_high (reclaim)

    Invalidation: if stop_price_origin is hit before entry.
    """
    direction = leg.direction
    d_dates = daily_bars["dates"]
    start_bar = leg.discovery_bar
    n_daily = daily_bars["n"]

    if start_bar >= len(d_dates):
        return EntryDecision(skipped=True, skip_reason="no_1h_data")

    # Find hourly start index at discovery date
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

    zone_low = leg.zone_low
    zone_high = leg.zone_high

    h_deadline = min(h_start + config.max_zone_wait_bars * 7, h_n - 2)

    # State machine
    sweep_seen = False

    for hb in range(h_start, h_deadline):
        lo = h_lows[hb]
        hi = h_highs[hb]
        c = h_closes[hb]

        # Stop invalidation
        if direction == "bullish" and lo <= leg.stop_price_origin:
            return EntryDecision(skipped=True, skip_reason="invalidated")
        if direction == "bearish" and hi >= leg.stop_price_origin:
            return EntryDecision(skipped=True, skip_reason="invalidated")

        if not sweep_seen:
            # Phase 1: look for sweep
            if direction == "bullish" and lo < zone_low:
                sweep_seen = True
            elif direction == "bearish" and hi > zone_high:
                sweep_seen = True
        else:
            # Phase 2: look for reclaim after sweep
            reclaimed = (direction == "bullish" and c >= zone_low) or (
                direction == "bearish" and c <= zone_high
            )
            if reclaimed and hb + 1 < h_n:
                entry_h_bar = hb + 1
                entry_price = h_opens[entry_h_bar]
                entry_date = h_dates[entry_h_bar][:8]

                # Map back to daily bar
                entry_daily_bar = None
                for i in range(start_bar, n_daily):
                    if d_dates[i] >= entry_date:
                        entry_daily_bar = i
                        break
                if entry_daily_bar is None:
                    return EntryDecision(skipped=True, skip_reason="no_trigger_fired")

                return EntryDecision(
                    enter=True,
                    entry_bar_daily=entry_daily_bar,
                    entry_price=entry_price,
                    trigger_type="1h_reclaim_after_sweep",
                )

    return EntryDecision(skipped=True, skip_reason="no_trigger_fired")
