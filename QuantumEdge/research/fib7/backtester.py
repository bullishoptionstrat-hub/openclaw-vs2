"""
fib7 backtester.

Extends fib6's backtester with:
  1. Multi-bar regime measurement (regime_bar: discovery/completion/anchor)
  2. ATR regime gate (atr_regime_gate: neutral/atr_active/atr_quiet)
  3. Hybrid vol+ATR gate support
  4. Separate counters: n_vol_filtered, n_atr_filtered

Returns (results, n_legs, n_skipped, n_regime_filtered)
for compatibility with fib6's interface.
n_regime_filtered = n_vol_filtered + n_atr_filtered.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from research.fib2.data import compute_atr
from research.fib2 import backtester as _fib2
from research.fib2 import filters
from research.fib6.execution import decide_entry
from research.fib7.regime import check_all_gates


def simulate(
    legs: list,
    daily_bars: dict,
    config,
    hourly_bars: Optional[dict] = None,
    date_to_1h: Optional[dict] = None,
    spy_daily: Optional[dict] = None,
) -> tuple[list, int, int, int]:
    """
    Simulate legs with fib7 multi-bar regime gate + fib6 execution.

    Parameters
    ----------
    legs        : list[QualifiedLeg] from fib3.detector
    daily_bars  : instrument daily OHLCV dict
    config      : Fib7Config (or Fib6Config subclass)
    hourly_bars : optional 1H OHLCV dict
    date_to_1h  : {date_str: (start_idx, end_idx)} mapping
    spy_daily   : optional SPY daily bars for regime filter

    Returns
    -------
    (list[StrictTradeResult], n_legs, n_skipped, n_regime_filtered)
    """
    d_highs = daily_bars["highs"]
    d_lows = daily_bars["lows"]
    d_closes = daily_bars["closes"]
    d_volumes = daily_bars["volumes"]
    d_opens = daily_bars["opens"]
    d_dates = daily_bars["dates"]
    n_daily = daily_bars["n"]

    d_atr = compute_atr(d_highs, d_lows, d_closes, config.atr_period)

    spy_closes = spy_daily["closes"] if spy_daily else None
    spy_dates = spy_daily["dates"] if spy_daily else None

    results = []
    n_legs = len(legs)
    n_skipped = 0
    n_regime_filtered = 0
    equity = config.initial_equity

    for leg in legs:
        db = leg.discovery_bar
        if db >= n_daily - 1:
            continue

        disc_date = d_dates[db]

        # ── Standard regime checks (from fib4/fib5) ─────────────────────────
        spy_bull = (
            filters.spy_bull_regime(spy_closes, spy_dates, disc_date)
            if spy_closes is not None
            else True
        )
        in_trend = filters.is_trending(d_highs, d_lows, d_closes, db, d_atr)
        vol_exp = filters.volume_expansion_on_leg(d_volumes, leg.completion_bar)
        in_disc = filters.in_discount(d_highs, d_lows, d_closes, db, leg.direction)
        not_comp = filters.not_compressed(d_atr, d_closes, db, config.compression_atr_pct)

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

        # ── fib7 multi-bar regime gates ──────────────────────────────────────
        passes, _ = check_all_gates(d_volumes, d_atr, leg, config)
        if not passes:
            n_regime_filtered += 1
            continue

        # ── Entry decision (fib6 execution engine) ───────────────────────────
        decision = decide_entry(
            leg,
            daily_bars,
            d_atr,
            config,
            hourly_bars=hourly_bars,
            date_to_1h=date_to_1h,
        )

        if decision.skipped:
            n_skipped += 1
            continue

        if not decision.enter:
            continue

        # ── Trade management (reuse fib2's _run_trade) ───────────────────────
        entry_bar = decision.entry_bar_daily
        entry_price = decision.entry_price

        if entry_bar >= n_daily:
            continue

        result = _fib2._run_trade(
            leg,
            entry_bar,
            entry_price,
            decision.trigger_type,
            d_opens,
            d_highs,
            d_lows,
            d_closes,
            n_daily,
            config,
            d_atr,
            equity,
            spy_bull,
            in_trend,
            vol_exp,
            in_disc,
        )

        if result is not None:
            equity = result.equity_after
            results.append(result)

    return results, n_legs, n_skipped, n_regime_filtered


def friction_adjusted_r(results: list, config) -> list[float]:
    """Return friction-adjusted R multiples. Reuses fib6 logic."""
    slippage_pct = getattr(config, "slippage_pct", 0.0)
    commission = getattr(config, "commission_per_trade", 0.0)
    if slippage_pct == 0.0 and commission == 0.0:
        return [t.r_multiple for t in results]
    adjusted = []
    for t in results:
        rps = max(t.risk_per_share, 1e-6)
        friction_r = (2.0 * slippage_pct * t.entry_price + commission) / rps
        adjusted.append(t.r_multiple - friction_r)
    return adjusted
