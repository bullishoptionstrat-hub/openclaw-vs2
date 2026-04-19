"""
fib6 portfolio construction.

Builds a portfolio from multiple per-instrument signal streams.
Research-level model: time-sort all trades, apply instrument weights,
build combined equity curve, compute portfolio-level stats.

Portfolio methods:
  equal       -- 1/N weight per instrument
  vol_scaled  -- weight inversely proportional to R-multiple std dev
  capped      -- vol_scaled but cap at max_weight (default 40%), renormalize

Single-best benchmark is reported separately for comparison.
"""

from __future__ import annotations

import math
from typing import Optional


# ---------------------------------------------------------------------------
# Weight computation
# ---------------------------------------------------------------------------


def compute_equal_weights(tickers: list[str]) -> dict[str, float]:
    """1/N weight per instrument."""
    if not tickers:
        return {}
    n = len(tickers)
    return {t: 1.0 / n for t in tickers}


def compute_vol_scaled_weights(
    results_by_ticker: dict[str, list],
    min_trades: int = 5,
) -> dict[str, float]:
    """
    Weight inversely proportional to std dev of R multiples.
    Instruments with < min_trades are excluded.
    """
    inv_vol = {}
    for ticker, results in results_by_ticker.items():
        if len(results) < min_trades:
            continue
        r_vals = [t.r_multiple for t in results]
        sigma = _std(r_vals)
        if sigma > 0:
            inv_vol[ticker] = 1.0 / sigma

    total = sum(inv_vol.values())
    if total <= 0:
        return compute_equal_weights(list(results_by_ticker.keys()))

    return {t: v / total for t, v in inv_vol.items()}


def compute_capped_weights(
    results_by_ticker: dict[str, list],
    max_weight: float = 0.40,
    min_trades: int = 5,
) -> dict[str, float]:
    """
    Vol-scaled weights, capped at max_weight per instrument.
    Excess weight is redistributed proportionally.
    """
    raw = compute_vol_scaled_weights(results_by_ticker, min_trades=min_trades)
    if not raw:
        return {}

    # Iterative cap: clip and renormalize until all within max_weight
    weights = dict(raw)
    for _ in range(20):  # Max iterations
        total = sum(weights.values())
        if total <= 0:
            break
        normalized = {t: w / total for t, w in weights.items()}
        capped = {t: min(w, max_weight) for t, w in normalized.items()}
        if all(abs(capped[t] - normalized[t]) < 1e-9 for t in capped):
            return capped
        weights = capped  # Re-iterate with capped values

    # Final normalization
    total = sum(weights.values())
    if total <= 0:
        return {}
    return {t: w / total for t, w in weights.items()}


# ---------------------------------------------------------------------------
# Portfolio equity builder
# ---------------------------------------------------------------------------


def build_portfolio(
    results_by_ticker: dict[str, list],
    dates_by_ticker: dict[str, list],
    weights: dict[str, float],
    risk_per_trade: float = 0.01,
    initial_equity: float = 100_000.0,
) -> dict:
    """
    Build a portfolio equity curve from per-instrument trade streams.

    Parameters
    ----------
    results_by_ticker : {ticker: list[StrictTradeResult]}
    dates_by_ticker   : {ticker: list[str]} -- daily_bars["dates"] for each ticker
    weights           : {ticker: float} -- portfolio allocation weights
    risk_per_trade    : fraction of equity risked per trade unit
    initial_equity    : starting portfolio equity

    Returns
    -------
    dict with portfolio-level stats (n_trades, exp_r, sharpe_r, max_drawdown, ...)
    """
    # Collect all trades with sortable date strings
    all_trades = []
    for ticker, results in results_by_ticker.items():
        if ticker not in weights:
            continue
        w = weights[ticker]
        if w <= 0:
            continue
        dates = dates_by_ticker.get(ticker, [])
        for t in results:
            entry_date = dates[t.entry_bar] if t.entry_bar < len(dates) else "00000000"
            all_trades.append({
                "ticker": ticker,
                "entry_date": entry_date,
                "entry_bar": t.entry_bar,
                "r_multiple": t.r_multiple,
                "weight": w,
            })

    if not all_trades:
        return {
            "n_trades": 0, "win_rate": 0.0, "exp_r": 0.0,
            "sharpe_r": 0.0, "sortino_r": 0.0,
            "profit_factor": 0.0, "max_drawdown": 0.0,
        }

    # Sort by entry date (time-ordered combined stream)
    all_trades.sort(key=lambda x: x["entry_date"])

    # Build combined equity curve
    equity = initial_equity
    equities = [equity]
    r_stream = []

    for trade in all_trades:
        # Weighted R contribution
        w_r = trade["r_multiple"] * trade["weight"]
        r_stream.append(w_r)
        pnl = w_r * risk_per_trade * equity
        equity = max(equity + pnl, 1.0)
        equities.append(equity)

    n = len(r_stream)
    wins = sum(1 for r in r_stream if r > 0)
    mean_r = sum(r_stream) / n
    std_r = _std(r_stream)
    neg_r = [r for r in r_stream if r < 0]
    down_std = _std(neg_r) if neg_r else 1e-9
    sharpe = mean_r / std_r if std_r > 0 else 0.0
    sortino = mean_r / down_std if down_std > 0 else 0.0

    gw = sum(r for r in r_stream if r > 0)
    gl = abs(sum(r for r in r_stream if r < 0))
    pf = gw / gl if gl > 0 else float("inf")

    peak = equities[0]
    max_dd = 0.0
    for e in equities:
        peak = max(peak, e)
        dd = (e - peak) / peak
        max_dd = min(max_dd, dd)

    # Per-instrument breakdown
    breakdown = {}
    for ticker, results in results_by_ticker.items():
        if results:
            r_vals = [t.r_multiple for t in results]
            breakdown[ticker] = {
                "n": len(results),
                "exp_r": round(sum(r_vals) / len(r_vals), 4),
                "weight": round(weights.get(ticker, 0.0), 4),
            }

    return {
        "n_trades": n,
        "win_rate": round(wins / n, 4),
        "exp_r": round(mean_r, 4),
        "sharpe_r": round(sharpe, 3),
        "sortino_r": round(sortino, 3),
        "profit_factor": round(pf, 3),
        "max_drawdown": round(max_dd, 5),
        "breakdown": breakdown,
    }


# ---------------------------------------------------------------------------
# Single-best benchmark
# ---------------------------------------------------------------------------


def find_single_best(
    results_by_ticker: dict[str, list],
) -> tuple[str, dict]:
    """
    Return (best_ticker, stats) for the instrument with highest exp_r.
    Requires min 5 trades.
    """
    best_ticker = None
    best_exp = float("-inf")
    best_stats = {}

    for ticker, results in results_by_ticker.items():
        if len(results) < 5:
            continue
        r_vals = [t.r_multiple for t in results]
        exp_r = sum(r_vals) / len(r_vals)
        if exp_r > best_exp:
            best_exp = exp_r
            best_ticker = ticker
            std_r = _std(r_vals)
            sharpe = exp_r / std_r if std_r > 0 else 0.0
            best_stats = {
                "n_trades": len(results),
                "exp_r": round(exp_r, 4),
                "sharpe_r": round(sharpe, 3),
            }

    return best_ticker or "none", best_stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 1e-9
    m = sum(vals) / len(vals)
    var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    return math.sqrt(max(var, 0.0))
