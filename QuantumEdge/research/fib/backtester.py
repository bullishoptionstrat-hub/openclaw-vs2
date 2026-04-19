"""
Event-driven backtester for the Fibonacci manipulation-leg model.

Processes setups in chronological order.  For each setup, scans forward
bar-by-bar from discovery_bar to determine whether price entered the zone,
and if so, tracks MAE/MFE and records the exit.

State machine per setup:
  WAITING_FOR_ZONE  : between discovery_bar and first zone touch
  IN_TRADE          : zone touched, entry executed at next bar open
  RESOLVED          : trade exited (stop/target/timeout) or invalidated

No portfolio-level position tracking in this version — each setup is
evaluated independently.  Portfolio equity is tracked cumulatively for
CAGR/Sharpe calculations.
"""

from __future__ import annotations

import math
import numpy as np
from typing import Optional

from research.fib.model import FibModelConfig, ManipulationSetup, TradeResult


def simulate(
    setups: list[ManipulationSetup],
    bars: dict,
    config: FibModelConfig,
) -> list[TradeResult]:
    """
    Simulate all detected setups against the bar series.

    Parameters
    ----------
    setups : from detector.find_manipulation_setups()
    bars   : from data.load_ticker()
    config : FibModelConfig

    Returns
    -------
    list[TradeResult] — one per setup that entered the zone (and therefore traded)
    plus invalidated records where relevant.
    """
    opens = bars["opens"]
    highs = bars["highs"]
    lows = bars["lows"]
    closes = bars["closes"]
    n_bars = bars["n"]

    results: list[TradeResult] = []
    equity = config.initial_equity

    for setup in setups:
        db = setup.discovery_bar
        if db >= n_bars - 1:
            continue  # not enough bars to simulate

        # ── Phase 1: wait for zone touch ──────────────────────────────────
        entry_bar = None
        entry_price = None
        invalidated = False

        zone_deadline = db + config.max_zone_wait_bars

        for bar in range(db, min(zone_deadline, n_bars)):
            c = closes[bar]
            lo = lows[bar]
            hi = highs[bar]

            # Invalidation: price breaks through the anchor (stop would be hit)
            if setup.direction == "bullish" and lo <= setup.stop_price:
                invalidated = True
                break
            if setup.direction == "bearish" and hi >= setup.stop_price:
                invalidated = True
                break

            # Zone touch detection (based on entry variant)
            touched = False
            if config.entry_variant in ("zone_close", "zone_touch"):
                # Enter if close is inside the zone
                touched = setup.zone_low <= c <= setup.zone_high
            elif config.entry_variant == "golden_only":
                touched = setup.zone_low <= c <= setup.zone_high
            elif config.entry_variant == "fib_382_touch":
                # Enter if the low (bullish) or high (bearish) touches fib_382
                if setup.direction == "bullish":
                    touched = lo <= setup.fib_382
                else:
                    touched = hi >= setup.fib_382

            if touched and bar + 1 < n_bars:
                # Entry at OPEN of the next bar (avoids same-bar execution)
                entry_bar = bar + 1
                entry_price = opens[entry_bar]
                break

        if invalidated or entry_bar is None:
            continue  # setup never entered

        # ── Phase 2: manage trade ────────────────────────────────────────
        stop = setup.stop_price
        target = setup.fib_1618 if config.target_fib == 1.618 else setup.fib_1272
        partial_at = setup.fib_1272 if config.scale_at_1272 else None

        # Risk per share
        if setup.direction == "bullish":
            risk_per_share = entry_price - stop
        else:
            risk_per_share = stop - entry_price

        if risk_per_share <= 0:
            continue  # degenerate — entry inside stop band

        # Position size (risk-based)
        risk_dollars = equity * config.risk_per_trade
        shares = risk_dollars / risk_per_share

        max_exit_bar = min(entry_bar + config.max_bars_in_trade, n_bars - 1)

        exit_bar = max_exit_bar
        exit_price = closes[max_exit_bar]
        exit_reason = "timeout"

        reached_1272 = False
        reached_1618 = False

        max_adverse = 0.0  # worst price move against us (in R units)
        max_favorable = 0.0  # best price move in our favor (in R units)

        partial_taken = False
        partial_r = 0.0

        for bar in range(entry_bar, max_exit_bar + 1):
            hi = highs[bar]
            lo = lows[bar]
            op = opens[bar]
            cls = closes[bar]

            if setup.direction == "bullish":
                adverse = (entry_price - lo) / risk_per_share
                favorable = (hi - entry_price) / risk_per_share
            else:
                adverse = (hi - entry_price) / risk_per_share
                favorable = (entry_price - lo) / risk_per_share

            max_adverse = max(max_adverse, adverse)
            max_favorable = max(max_favorable, favorable)

            # Track whether extensions were reached (even if we didn't exit there)
            if setup.direction == "bullish":
                if hi >= setup.fib_1272:
                    reached_1272 = True
                if hi >= setup.fib_1618:
                    reached_1618 = True
            else:
                if lo <= setup.fib_1272:
                    reached_1272 = True
                if lo <= setup.fib_1618:
                    reached_1618 = True

            # Check stop
            stop_hit = (setup.direction == "bullish" and lo <= stop) or (
                setup.direction == "bearish" and hi >= stop
            )
            if stop_hit:
                exit_price = stop
                exit_bar = bar
                exit_reason = "stop"
                break

            # Check target (or partial)
            if partial_at is not None and not partial_taken:
                partial_hit = (setup.direction == "bullish" and hi >= partial_at) or (
                    setup.direction == "bearish" and lo <= partial_at
                )
                if partial_hit:
                    # Half position taken at 1.272; move stop to entry (breakeven)
                    partial_taken = True
                    partial_r = (
                        (partial_at - entry_price) / risk_per_share
                        if setup.direction == "bullish"
                        else (entry_price - partial_at) / risk_per_share
                    )
                    stop = entry_price  # breakeven stop

            target_hit = (setup.direction == "bullish" and hi >= target) or (
                setup.direction == "bearish" and lo <= target
            )
            if target_hit:
                exit_price = target
                exit_bar = bar
                exit_reason = str(config.target_fib)
                break

        # Compute R multiple
        if setup.direction == "bullish":
            gross_r = (exit_price - entry_price) / risk_per_share
        else:
            gross_r = (entry_price - exit_price) / risk_per_share

        if partial_taken:
            # 50% at 1.272, 50% at final exit
            r_multiple = 0.5 * partial_r + 0.5 * gross_r
        else:
            r_multiple = gross_r

        pnl_pct = (r_multiple * risk_per_share) / entry_price

        # Update equity
        trade_pnl = r_multiple * risk_dollars
        equity_before = equity
        equity += trade_pnl
        equity = max(equity, 1.0)  # prevent negative equity blowup in testing

        results.append(
            TradeResult(
                setup=setup,
                entry_bar=entry_bar,
                entry_price=entry_price,
                exit_bar=exit_bar,
                exit_price=exit_price,
                exit_reason=exit_reason,
                risk_per_share=risk_per_share,
                r_multiple=r_multiple,
                mae_r=-max_adverse,
                mfe_r=max_favorable,
                bars_held=exit_bar - entry_bar,
                reached_1272=reached_1272,
                reached_1618=reached_1618,
                pnl_pct=pnl_pct,
                equity_before=equity_before,
                equity_after=equity,
            )
        )

    return results
