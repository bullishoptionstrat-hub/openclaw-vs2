"""
fib4 backtester.

Wraps fib3 leg detection + fib4 entry decision engine + fib2 trade management.

Returns (results, n_legs, n_skipped) where:
  results   — list[StrictTradeResult] for completed trades
  n_legs    — total legs after quality filtering
  n_skipped — legs where zone was reached but no trigger fired, OR
              trigger fired but entry was explicitly skipped (passive timeout,
              nextbar confirm failed, etc.)

The distinction matters:
  n_legs - len(results) - n_skipped = legs where zone was never reached
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from research.fib2.data import compute_atr
from research.fib2 import backtester as _fib2
from research.fib2 import filters
from research.fib4.model import Fib4Config
from research.fib4.execution import decide_entry


def simulate(
    legs: list,
    daily_bars: dict,
    config: Fib4Config,
    hourly_bars: Optional[dict] = None,
    date_to_1h: Optional[dict] = None,
    spy_daily: Optional[dict] = None,
) -> tuple[list, int, int]:
    """
    Simulate all qualified legs using fib4's execution engine.

    Parameters
    ----------
    legs        : list[QualifiedLeg] from fib3.detector
    daily_bars  : instrument daily OHLCV dict
    config      : Fib4Config
    hourly_bars : optional 1H OHLCV dict (None -> daily fallback for 1H triggers)
    date_to_1h  : {date_str: (start_idx, end_idx)} mapping
    spy_daily   : optional SPY daily bars for regime filter

    Returns
    -------
    (list[StrictTradeResult], n_legs, n_skipped)
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

    results = []
    n_legs = len(legs)
    n_skipped = 0
    equity = config.initial_equity

    for leg in legs:
        db = leg.discovery_bar
        if db >= n_daily - 1:
            continue

        # ── Regime checks at discovery bar ──────────────────────────────────
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

        # ── fib4 entry decision ──────────────────────────────────────────────
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
            # No zone interaction at all (trigger never fired, not skipped)
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

    return results, n_legs, n_skipped


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _rolling_vol_avg(volumes: np.ndarray, period: int) -> np.ndarray:
    n = len(volumes)
    avg = np.full(n, np.nan)
    for i in range(period - 1, n):
        avg[i] = float(np.mean(volumes[i - period + 1 : i + 1]))
    return avg
