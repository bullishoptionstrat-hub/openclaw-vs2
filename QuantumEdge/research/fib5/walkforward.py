"""
fib5 walk-forward and IS/OOS split analysis.

run_oos_split()    — IS period + two OOS periods for one strategy x ticker
run_oos_batch()    — run all strategy x ticker combinations
"""

from __future__ import annotations

import copy
from typing import Optional

from research.fib2.data import load_daily, load_hourly, build_date_to_1h_range
from research.fib3.detector import find_qualified_legs
from research.fib5.backtester import simulate, friction_adjusted_r
from research.fib5.analysis import compute_stats_from_r, compute_stats


# ---------------------------------------------------------------------------
# Core OOS split
# ---------------------------------------------------------------------------


def run_period(
    ticker: str,
    config,
    start_date: Optional[str],
    end_date: Optional[str],
    spy_daily_full: Optional[dict],
    hourly_bars: Optional[dict] = None,
    date_to_1h: Optional[dict] = None,
) -> dict:
    """
    Run one period (start_date to end_date) for ticker + config.
    Returns stats dict. Returns None on data error.
    """
    try:
        daily = load_daily(
            ticker,
            start_date=start_date,
            end_date=end_date,
        )
    except (FileNotFoundError, ValueError):
        return None

    # For hourly, filter by date range
    h_bars = None
    d_to_1h = None
    if hourly_bars is not None and date_to_1h is not None:
        # Filter hourly bars if possible (use full hourly, backtester will skip OOB dates)
        h_bars = hourly_bars
        d_to_1h = date_to_1h

    legs = find_qualified_legs(
        daily,
        config,
        spy_daily=spy_daily_full if ticker != "SPY" else None,
    )

    results, n_legs, n_skipped = simulate(
        legs,
        daily,
        config,
        hourly_bars=h_bars,
        date_to_1h=d_to_1h,
        spy_daily=spy_daily_full if ticker != "SPY" else None,
    )

    adj_r = friction_adjusted_r(results, config)
    stats = compute_stats(results, n_legs, n_skipped)
    stats["adj_expectancy_r"] = round(sum(adj_r) / len(adj_r), 4) if adj_r else 0.0
    return stats


def run_oos_split(
    strategy_name: str,
    ticker: str,
    config,
    spy_daily_full: Optional[dict],
    hourly_bars: Optional[dict] = None,
    date_to_1h: Optional[dict] = None,
) -> dict:
    """
    Run IS, OOS1, and OOS2 periods.
    Returns dict with 'is', 'oos1', 'oos2' keys (each a stats dict or None).
    """
    is_start = config.is_start or None
    is_end = config.is_end or None
    oos1_start = config.oos1_start or None
    oos1_end = config.oos1_end or None
    oos2_start = config.oos2_start or None
    oos2_end = config.oos2_end or None

    return {
        "strategy": strategy_name,
        "ticker": ticker,
        "is": run_period(ticker, config, is_start, is_end, spy_daily_full, hourly_bars, date_to_1h),
        "oos1": run_period(
            ticker, config, oos1_start, oos1_end, spy_daily_full, hourly_bars, date_to_1h
        ),
        "oos2": run_period(
            ticker, config, oos2_start, oos2_end or None, spy_daily_full, hourly_bars, date_to_1h
        ),
    }


def run_oos_batch(
    strategies: dict,
    tickers: list[str],
    spy_daily_full: Optional[dict],
    spy_hourly: Optional[dict] = None,
    spy_date_to_1h: Optional[dict] = None,
) -> list[dict]:
    """
    Run all strategy x ticker combinations through IS/OOS split.
    Returns list of split result dicts.
    """
    results = []
    for strategy_name, config in strategies.items():
        for ticker in tickers:
            h_bars = spy_hourly if ticker == "SPY" else None
            d_to_1h = spy_date_to_1h if ticker == "SPY" else None
            split = run_oos_split(strategy_name, ticker, config, spy_daily_full, h_bars, d_to_1h)
            results.append(split)
    return results


# ---------------------------------------------------------------------------
# Stats helpers for use in this module
# ---------------------------------------------------------------------------


def compute_stats_from_r(adj_r_vals: list[float]) -> dict:
    """Minimal stats from a list of R multiples."""
    if not adj_r_vals:
        return {"n": 0, "win_rate": 0.0, "exp_r": 0.0}
    n = len(adj_r_vals)
    wins = sum(1 for r in adj_r_vals if r > 0)
    return {
        "n": n,
        "win_rate": round(wins / n, 4),
        "exp_r": round(sum(adj_r_vals) / n, 4),
    }
