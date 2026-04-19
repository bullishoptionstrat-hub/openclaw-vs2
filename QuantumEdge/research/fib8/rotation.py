"""
fib8 thresholded rotation engine v2.

Wraps fib7's rotation engine with a hard eligibility gate:
  - min_exp_r:             trailing 20-trade ExpR >= threshold
  - min_n_trades:          at least N historical trades
  - min_friction_adj_exp_r: positive after 5bps friction adjustment

Purpose: exclude weak performers (XLF at +0.104R) before the rotation pool
is scored. fib7 rotation failed because XLF diluted the pool.

Expected result with gate (min_exp_r=0.15):
  Pool shrinks from 5 -> 4 instruments: {XLK, IWM, XLY, QQQ}
  top2_eligible approaches single_best_static performance.
"""

from __future__ import annotations

import math
from typing import Optional

from research.fib7.rotation import (
    run_top_n_rotation,
    find_single_best,
    compute_rotation_score,
    _std,
    _trailing_exp_r,
)


# ---------------------------------------------------------------------------
# Eligibility gate
# ---------------------------------------------------------------------------


def apply_eligibility_gate(
    results_by_ticker: dict[str, list],
    min_exp_r: float = 0.15,
    min_n_trades: int = 15,
    min_friction_adj_exp_r: float = 0.0,
    friction_bps: float = 5.0,
) -> tuple[dict, dict]:
    """
    Filter instruments by eligibility criteria.

    Parameters
    ----------
    results_by_ticker      : {ticker: list[StrictTradeResult]}
    min_exp_r              : minimum trailing 20-trade ExpR to qualify
    min_n_trades           : minimum historical trades to qualify
    min_friction_adj_exp_r : minimum ExpR after friction (friction_bps round-trip)
    friction_bps           : round-trip slippage in bps for friction adjustment

    Returns
    -------
    (eligible_pool, excluded_summary)
      eligible_pool     : {ticker: list[StrictTradeResult]} -- passing instruments
      excluded_summary  : {ticker: reason_str} -- excluded instruments with reason
    """
    friction_penalty = friction_bps / 10_000.0  # per trade (one-way adjustment)

    eligible = {}
    excluded = {}

    for ticker, results in results_by_ticker.items():
        if not results:
            excluded[ticker] = "no trades"
            continue

        n = len(results)
        r_vals = [t.r_multiple for t in results]
        exp_r = sum(r_vals) / n

        # Adjust for friction: each trade loses ~2x friction (entry + exit)
        friction_adj_exp_r = exp_r - 2 * friction_penalty

        reasons = []
        if n < min_n_trades:
            reasons.append(f"n={n} < min_n={min_n_trades}")
        if exp_r < min_exp_r:
            reasons.append(f"exp_r={exp_r:+.4f} < min={min_exp_r:+.4f}")
        if friction_adj_exp_r < min_friction_adj_exp_r:
            reasons.append(
                f"friction_adj_exp_r={friction_adj_exp_r:+.4f} < min={min_friction_adj_exp_r:+.4f}"
            )

        if reasons:
            excluded[ticker] = "; ".join(reasons)
        else:
            eligible[ticker] = results

    return eligible, excluded


# ---------------------------------------------------------------------------
# Thresholded rotation runner
# ---------------------------------------------------------------------------


def run_thresholded_rotation(
    results_by_ticker: dict[str, list],
    dates_by_ticker: dict[str, list],
    top_n: int = 2,
    max_weight_cap: Optional[float] = None,
    min_exp_r: float = 0.15,
    min_n_trades: int = 15,
    min_friction_adj_exp_r: float = 0.0,
    rebalance_every: int = 20,
    risk_per_trade: float = 0.01,
    initial_equity: float = 100_000.0,
) -> dict:
    """
    Run top-N rotation with eligibility gate applied first.

    Returns run_top_n_rotation result dict plus:
      "eligible_tickers"  : list of tickers that passed the gate
      "excluded_tickers"  : {ticker: reason} for excluded instruments
      "gate_params"       : the gate parameters used
    """
    eligible, excluded = apply_eligibility_gate(
        results_by_ticker,
        min_exp_r=min_exp_r,
        min_n_trades=min_n_trades,
        min_friction_adj_exp_r=min_friction_adj_exp_r,
    )

    if not eligible:
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
            "top_n": top_n,
            "eligible_tickers": [],
            "excluded_tickers": excluded,
            "gate_params": {
                "min_exp_r": min_exp_r,
                "min_n_trades": min_n_trades,
                "min_friction_adj_exp_r": min_friction_adj_exp_r,
            },
        }

    eligible_dates = {t: dates_by_ticker[t] for t in eligible if t in dates_by_ticker}

    stats = run_top_n_rotation(
        eligible,
        eligible_dates,
        top_n=top_n,
        max_weight_cap=max_weight_cap,
        rebalance_every=rebalance_every,
        risk_per_trade=risk_per_trade,
        initial_equity=initial_equity,
    )

    stats["eligible_tickers"] = sorted(eligible.keys())
    stats["excluded_tickers"] = excluded
    stats["gate_params"] = {
        "min_exp_r": min_exp_r,
        "min_n_trades": min_n_trades,
        "min_friction_adj_exp_r": min_friction_adj_exp_r,
    }
    return stats


# ---------------------------------------------------------------------------
# Rotation comparison runner
# ---------------------------------------------------------------------------


def run_rotation_comparison(
    results_by_ticker: dict[str, list],
    dates_by_ticker: dict[str, list],
) -> dict:
    """
    Run 4 rotation variants + 2 benchmarks.

    Variants:
      top1_eligible          -- top-1 with gate (min_exp_r=0.15)
      top2_eligible          -- top-2 with gate
      top2_eligible_capped60 -- top-2 with gate + 60% weight cap
      top3_eligible          -- top-3 with gate

    Benchmarks:
      single_best_static     -- best single instrument (max IS exp_r)
      equal_weight_raw       -- equal weight all instruments (no gate, fib6 style)

    Returns
    -------
    dict: {variant_name: stats_dict}
    """
    results = {}

    # Benchmarks
    best_ticker, best_stats = find_single_best(results_by_ticker)
    # Add win_rate for display (not computed by fib7's find_single_best)
    if best_ticker in results_by_ticker:
        best_r_vals = [t.r_multiple for t in results_by_ticker[best_ticker]]
        best_wins = sum(1 for r in best_r_vals if r > 0)
        best_stats["win_rate"] = round(best_wins / len(best_r_vals), 4) if best_r_vals else 0.0
    results["single_best_static"] = {
        **best_stats,
        "ticker": best_ticker,
        "description": f"Static single-best: {best_ticker}",
    }

    # Equal-weight all raw (fib6-style diluted)
    if results_by_ticker:
        n_inst = len(results_by_ticker)
        all_r = []
        for ticker, res in results_by_ticker.items():
            for t in res:
                all_r.append(t.r_multiple / n_inst)
        if all_r:
            n = len(all_r)
            mean_r = sum(all_r) / n
            std_r = _std(all_r)
            wins = sum(1 for r in all_r if r > 0)
            results["equal_weight_raw"] = {
                "n_trades": n,
                "exp_r": round(mean_r, 4),
                "win_rate": round(wins / n, 4),
                "sharpe_r": round(mean_r / std_r if std_r > 0 else 0, 3),
                "description": f"Equal-weight all {n_inst} instruments (no gate)",
            }

    # Gated rotation variants
    gate_params = {"min_exp_r": 0.15, "min_n_trades": 15, "min_friction_adj_exp_r": 0.0}

    for name, top_n, cap in [
        ("top1_eligible", 1, None),
        ("top2_eligible", 2, None),
        ("top2_eligible_capped60", 2, 0.60),
        ("top3_eligible", 3, None),
    ]:
        stats = run_thresholded_rotation(
            results_by_ticker,
            dates_by_ticker,
            top_n=top_n,
            max_weight_cap=cap,
            **gate_params,
        )
        stats["description"] = (
            f"top{top_n} eligible{' cap60%' if cap else ''} "
            f"(pool={stats.get('eligible_tickers', [])})"
        )
        results[name] = stats

    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def print_rotation_comparison(comparison: dict) -> None:
    """Print Track F rotation comparison table."""
    w = 90
    print(f"\n{'=' * w}")
    print(f"  FIB8 TRACK F -- THRESHOLDED ROTATION v2")
    print(f"  Eligibility gate: min_exp_r >= 0.15 | min_n_trades >= 15")
    print(f"{'=' * w}")

    # Print eligibility gate result (from first gated variant)
    for v in ["top2_eligible", "top1_eligible"]:
        if v in comparison and "eligible_tickers" in comparison[v]:
            stats = comparison[v]
            print(f"\n  Gate result:")
            print(f"    Eligible : {stats.get('eligible_tickers', [])}")
            excl = stats.get("excluded_tickers", {})
            if excl:
                for t, reason in excl.items():
                    print(f"    Excluded : {t} -- {reason}")
            break

    print(f"\n  {'Variant':<30} {'N':>5} {'ExpR':>7} {'Win%':>6} {'Sharpe':>7} {'Notes'}")
    print(f"  {'-' * 70}")

    order = [
        "single_best_static",
        "equal_weight_raw",
        "top1_eligible",
        "top2_eligible",
        "top2_eligible_capped60",
        "top3_eligible",
    ]
    for name in order:
        if name not in comparison:
            continue
        s = comparison[name]
        n = s.get("n_trades", 0)
        expr = s.get("exp_r", 0.0)
        winr = s.get("win_rate", 0.0)
        sharpe = s.get("sharpe_r", 0.0)
        ticker = s.get("ticker", "")
        desc = s.get("description", "")
        note = f"[{ticker}]" if ticker else ""
        print(f"  {name:<30} {n:>5} {expr:>+7.4f} {winr:>6.1%} {sharpe:>7.3f}  {note}")

    print(
        f"\n  Key: single_best_static = benchmark. Rotation wins if top2_eligible >= 75% of single_best ExpR."
    )
    print(f"{'=' * w}\n")
