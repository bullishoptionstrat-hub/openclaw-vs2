"""
fib7 selective rotation engine.

Replaces fib6's diluted equal/vol-scaled portfolio with a quality-scored
top-N instrument rotation engine.

Rotation logic:
  1. For each time period, score each instrument on:
     - trailing_exp_r   (rolling 20-trade expectancy R)
     - current_regime   (does instrument's current vol regime match gate?)
     - trade_density    (recent trade frequency; proxy for signal activity)
  2. Sort instruments by composite rotation score
  3. Hold only top-N instruments at any given time
  4. Rebalance weights when a new period begins or composition changes

Rotation methods:
  top1     -- hold single best-scoring instrument (concentrated)
  top2     -- hold top-2 instruments (equal weight within selection)
  top3     -- hold top-3 instruments (equal weight within selection)
  capped2  -- top-2 but cap at 60% per instrument

The rotation engine is evaluated against:
  - single_best_static: fixed single-instrument benchmark (fib6 basis)
  - equal_weight_5inst: diluted fib6 portfolio (shows why rotation wins)
"""

from __future__ import annotations

import math
from typing import Optional


# ---------------------------------------------------------------------------
# Rolling stats helpers
# ---------------------------------------------------------------------------


def _trailing_exp_r(r_vals: list[float], n: int = 20) -> float:
    """Mean R of the last n trades. Returns 0 if fewer than 5."""
    recent = r_vals[-n:]
    if len(recent) < 5:
        return 0.0
    return sum(recent) / len(recent)


def _rolling_std(r_vals: list[float], n: int = 20) -> float:
    recent = r_vals[-n:]
    if len(recent) < 2:
        return 1.0
    m = sum(recent) / len(recent)
    var = sum((v - m) ** 2 for v in recent) / (len(recent) - 1)
    return math.sqrt(max(var, 1e-9))


def _trade_density(r_vals: list[float], total_bars: int, window: int = 60) -> float:
    """Trades per bar in last `window` bars (uses count approximation)."""
    if total_bars <= 0:
        return 0.0
    recent_n = min(len(r_vals), int(len(r_vals) * window / max(total_bars, 1)) + 1)
    return recent_n / max(window, 1)


# ---------------------------------------------------------------------------
# Rotation score
# ---------------------------------------------------------------------------


def compute_rotation_score(
    ticker: str,
    r_vals: list[float],
    total_bars: int = 252,
    weight_exp_r: float = 0.6,
    weight_density: float = 0.2,
    weight_consistency: float = 0.2,
) -> float:
    """
    Composite rotation score for an instrument.

    Higher score = better candidate for inclusion in the rotation set.

    Components:
      trailing_exp_r   (60% weight) -- recent alpha signal
      trade_density    (20% weight) -- signal frequency (normalized)
      win_consistency  (20% weight) -- trailing win rate above 40%

    Score is scaled to [0, 1] approximately (not hard-bounded).
    """
    if len(r_vals) < 5:
        return 0.0

    exp_r = _trailing_exp_r(r_vals)
    density = _trade_density(r_vals, total_bars)

    wins = sum(1 for r in r_vals[-20:] if r > 0)
    n_recent = min(len(r_vals), 20)
    win_rate = wins / n_recent if n_recent > 0 else 0.0
    # Normalize: 50% win = 0.5, 40% = 0, 60% = 1.0
    consistency = max(0.0, (win_rate - 0.40) / 0.20)

    score = (
        weight_exp_r * max(exp_r, -1.0)
        + weight_density * min(density * 5, 1.0)
        + weight_consistency * consistency
    )
    return score


# ---------------------------------------------------------------------------
# Top-N rotation builder
# ---------------------------------------------------------------------------


def run_top_n_rotation(
    results_by_ticker: dict[str, list],
    dates_by_ticker: dict[str, list],
    top_n: int = 2,
    max_weight_cap: Optional[float] = None,
    rebalance_every: int = 20,
    risk_per_trade: float = 0.01,
    initial_equity: float = 100_000.0,
) -> dict:
    """
    Run a top-N rotation engine over all instrument trade streams.

    The engine:
      1. Collects all trades time-sorted across instruments
      2. At each `rebalance_every` trades, re-scores all instruments
         using their trailing stats and rebuilds the active set
      3. Only executes trades for instruments in the current active set
      4. Applies equal weight within the active set (or capped if specified)

    Parameters
    ----------
    results_by_ticker  : {ticker: list[StrictTradeResult]}
    dates_by_ticker    : {ticker: list[str]} -- daily_bars["dates"] per ticker
    top_n              : number of instruments to hold simultaneously
    max_weight_cap     : if set, cap per-instrument weight at this fraction
    rebalance_every    : rebalance active set every N trades
    risk_per_trade     : fraction of equity risked per unit
    initial_equity     : starting equity

    Returns
    -------
    dict with rotation portfolio stats + rotation_log
    """
    # Build time-sorted trade stream across all instruments
    all_trades = []
    for ticker, results in results_by_ticker.items():
        dates = dates_by_ticker.get(ticker, [])
        for t in results:
            entry_date = dates[t.entry_bar] if t.entry_bar < len(dates) else "00000000"
            all_trades.append(
                {
                    "ticker": ticker,
                    "entry_date": entry_date,
                    "entry_bar": t.entry_bar,
                    "r_multiple": t.r_multiple,
                }
            )

    all_trades.sort(key=lambda x: x["entry_date"])

    if not all_trades:
        return _empty_rotation_stats()

    # Track rolling R history per ticker
    r_history: dict[str, list[float]] = {t: [] for t in results_by_ticker}
    trade_counts: dict[str, int] = {t: 0 for t in results_by_ticker}

    # Initial active set: top-n by equal score until we have history
    active_set: set[str] = set(list(results_by_ticker.keys())[:top_n])

    equity = initial_equity
    equities = [equity]
    r_stream = []
    active_set_log = []

    trades_since_rebalance = 0

    for trade in all_trades:
        ticker = trade["ticker"]

        # Rebalance check
        if trades_since_rebalance >= rebalance_every:
            scores = {}
            for t, r_vals in r_history.items():
                scores[t] = compute_rotation_score(t, r_vals, total_bars=252)
            if scores:
                sorted_tickers = sorted(scores.keys(), key=lambda x: -scores[x])
                eligible = [t for t in sorted_tickers if len(r_history[t]) >= 5]
                if not eligible:
                    eligible = sorted_tickers
                new_active = set(eligible[:top_n])
                if new_active != active_set:
                    active_set_log.append(
                        {
                            "trade_n": len(r_stream),
                            "date": trade["entry_date"],
                            "old_set": sorted(active_set),
                            "new_set": sorted(new_active),
                            "scores": {t: round(scores.get(t, 0), 4) for t in sorted_tickers[:5]},
                        }
                    )
                    active_set = new_active
            trades_since_rebalance = 0

        # Only execute if ticker is in active set
        r_history[ticker].append(trade["r_multiple"])
        trade_counts[ticker] += 1
        trades_since_rebalance += 1

        if ticker not in active_set:
            continue

        # Weight within active set
        n_active = len(active_set)
        w = 1.0 / n_active if n_active > 0 else 1.0
        if max_weight_cap is not None:
            w = min(w, max_weight_cap)

        w_r = trade["r_multiple"] * w
        r_stream.append(w_r)
        pnl = w_r * risk_per_trade * equity
        equity = max(equity + pnl, 1.0)
        equities.append(equity)

    if not r_stream:
        return _empty_rotation_stats()

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

    # Per-ticker final rotation stats
    ticker_summary = {}
    for ticker, r_vals in r_history.items():
        if r_vals:
            ticker_summary[ticker] = {
                "n_trades_total": len(r_vals),
                "n_trades_active": trade_counts.get(ticker, 0),
                "trailing_exp_r": round(_trailing_exp_r(r_vals), 4),
                "final_score": round(compute_rotation_score(ticker, r_vals), 4),
            }

    return {
        "n_trades": n,
        "win_rate": round(wins / n, 4),
        "exp_r": round(mean_r, 4),
        "sharpe_r": round(sharpe, 3),
        "sortino_r": round(sortino, 3),
        "profit_factor": round(pf, 3),
        "max_drawdown": round(max_dd, 5),
        "rotation_changes": len(active_set_log),
        "rotation_log": active_set_log[-5:],  # Last 5 changes
        "ticker_summary": ticker_summary,
        "top_n": top_n,
    }


def _empty_rotation_stats() -> dict:
    return {
        "n_trades": 0,
        "win_rate": 0.0,
        "exp_r": 0.0,
        "sharpe_r": 0.0,
        "sortino_r": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 0.0,
        "rotation_changes": 0,
        "rotation_log": [],
        "ticker_summary": {},
        "top_n": 0,
    }


# ---------------------------------------------------------------------------
# Static single-best benchmark (same as fib6.portfolio.find_single_best)
# ---------------------------------------------------------------------------


def find_single_best(results_by_ticker: dict[str, list]) -> tuple[str, dict]:
    """Return (best_ticker, stats) for highest exp_r instrument with >= 5 trades."""
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
