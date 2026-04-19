"""
Fibonacci Manipulation-Leg Research Engine — CLI entry point.

Usage:
  cd QuantumEdge/
  python -m research.fib.run                          # all experiments, SPY
  python -m research.fib.run --ticker SPY XLK EWJ     # multiple tickers
  python -m research.fib.run --exp baseline_both      # single experiment
  python -m research.fib.run --list                   # list experiments
  python -m research.fib.run --start 20150101 --end 20221231  # date range

Results printed to stdout and saved as JSON to output/fib/<experiment>_<ticker>.json.

IMPORTANT: This runner is completely independent of the Lean backtest runner.
It does not require Lean, .NET, or any of the QuantConnect libraries.
It runs directly on the Lean daily zip data files.
"""

from __future__ import annotations

import sys
import os
import json
import argparse
import math
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_QE_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _QE_ROOT not in sys.path:
    sys.path.insert(0, _QE_ROOT)

from research.fib.data import load_ticker, available_tickers
from research.fib.detector import find_manipulation_setups
from research.fib.backtester import simulate
from research.fib.experiments import get_fib_config, list_fib_experiments, FIB_EXPERIMENTS
from research.fib.model import FibModelConfig, TradeResult

OUTPUT_DIR = os.path.join(_QE_ROOT, "output", "fib")


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def compute_stats(results: list[TradeResult], n_setups: int, n_zone_hit: int) -> dict:
    """Compute all required statistics from a list of TradeResult objects."""
    if not results:
        return {
            "n_setups": n_setups,
            "n_zone_hit": n_zone_hit,
            "n_trades": 0,
            "zone_hit_rate": n_zone_hit / max(n_setups, 1),
        }

    n = len(results)
    r_vals = [t.r_multiple for t in results]
    wins = [t for t in results if t.is_winner()]
    losses = [t for t in results if t.is_loser()]

    win_rate = len(wins) / n
    mean_r = sum(r_vals) / n
    med_r = sorted(r_vals)[n // 2]

    # Sharpe / Sortino on R multiples (risk-adjusted)
    std_r = _std(r_vals)
    neg_r = [r for r in r_vals if r < 0]
    down_r = _std(neg_r) if neg_r else 1e-9
    sharpe = mean_r / std_r if std_r > 0 else 0.0
    sortino = mean_r / down_r if down_r > 0 else 0.0

    # Profit factor
    gross_win = sum(r for r in r_vals if r > 0)
    gross_loss = abs(sum(r for r in r_vals if r < 0))
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")

    # MAE / MFE
    mae_vals = [t.mae_r for t in results]
    mfe_vals = [t.mfe_r for t in results]
    mean_mae = sum(mae_vals) / n
    mean_mfe = sum(mfe_vals) / n

    # Extension hit rates (across all trades, regardless of exit point)
    hit_1272 = sum(1 for t in results if t.reached_1272) / n
    hit_1618 = sum(1 for t in results if t.reached_1618) / n

    # CAGR / drawdown from equity curve
    eq_vals = [results[0].equity_before] + [t.equity_after for t in results]
    cagr, max_dd = _equity_stats(eq_vals, [t.entry_bar for t in results])

    # Average bars held
    avg_bars = sum(t.bars_held for t in results) / n

    # Exit reason breakdown
    exit_reasons: dict[str, int] = {}
    for t in results:
        exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1

    # Direction breakdown
    dir_bull = [t for t in results if t.setup.direction == "bullish"]
    dir_bear = [t for t in results if t.setup.direction == "bearish"]

    return {
        "n_setups": n_setups,
        "n_zone_hit": n_zone_hit,
        "n_trades": n,
        "zone_hit_rate": round(n_zone_hit / max(n_setups, 1), 4),
        "win_rate": round(win_rate, 4),
        "expectancy_r": round(mean_r, 4),
        "median_r": round(med_r, 4),
        "profit_factor": round(pf, 3),
        "sharpe_r": round(sharpe, 3),
        "sortino_r": round(sortino, 3),
        "mean_mae_r": round(mean_mae, 4),
        "mean_mfe_r": round(mean_mfe, 4),
        "hit_rate_1272": round(hit_1272, 4),
        "hit_rate_1618": round(hit_1618, 4),
        "cagr": round(cagr, 5),
        "max_drawdown": round(max_dd, 5),
        "avg_bars_held": round(avg_bars, 1),
        "exit_reasons": exit_reasons,
        "n_bullish_trades": len(dir_bull),
        "n_bearish_trades": len(dir_bear),
        "start_equity": eq_vals[0],
        "end_equity": round(eq_vals[-1], 2),
    }


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 1e-9
    m = sum(vals) / len(vals)
    var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    return math.sqrt(max(var, 0))


def _equity_stats(eq_vals: list[float], bar_indices: list[int]) -> tuple[float, float]:
    """
    Compute CAGR and max drawdown from an equity curve.
    bar_indices are used to estimate years elapsed.
    Returns (cagr, max_drawdown) where max_drawdown is negative.
    """
    if len(eq_vals) < 2:
        return 0.0, 0.0

    start_eq = eq_vals[0]
    end_eq = eq_vals[-1]

    # Approximate years from bar count (252 trading days/year)
    if bar_indices:
        n_bars = bar_indices[-1] - bar_indices[0] + 1
        years = max(n_bars / 252.0, 0.1)
    else:
        years = 1.0

    if start_eq <= 0 or end_eq <= 0:
        return 0.0, 0.0

    cagr = (end_eq / start_eq) ** (1.0 / years) - 1.0

    # Max drawdown
    peak = eq_vals[0]
    max_dd = 0.0
    for v in eq_vals:
        if v > peak:
            peak = v
        dd = (v - peak) / peak
        if dd < max_dd:
            max_dd = dd

    return cagr, max_dd


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------


def print_report(
    experiment_name: str,
    ticker: str,
    stats: dict,
    config: FibModelConfig,
) -> None:
    s = stats
    sep = "-" * 70
    print(f"\n{'=' * 70}")
    print(f"  FIB MODEL RESULTS  |  exp={experiment_name}  ticker={ticker}")
    print(f"{'=' * 70}")
    print(
        f"  Config: pivot_n={config.pivot_n}  entry={config.entry_variant}"
        f"  zone=[{config.entry_fib_low},{config.entry_fib_high}]"
        f"  target={config.target_fib}  min_leg_atr={config.min_leg_atr}"
    )
    print(sep)
    print(f"  Setups detected    : {s['n_setups']}")
    print(f"  Zone hit rate      : {s['n_zone_hit']}/{s['n_setups']}  = {s['zone_hit_rate']:.1%}")
    print(f"  Trades executed    : {s['n_trades']}")
    if s["n_trades"] == 0:
        print("  No trades — insufficient data or filters too strict.")
        print(f"{'=' * 70}\n")
        return
    print(sep)
    print(f"  Win rate           : {s['win_rate']:.1%}")
    print(f"  Expectancy (R)     : {s['expectancy_r']:+.3f}R")
    print(f"  Median R           : {s['median_r']:+.3f}R")
    print(f"  Profit factor      : {s['profit_factor']:.2f}")
    print(f"  Sharpe (on R)      : {s['sharpe_r']:.3f}")
    print(f"  Sortino (on R)     : {s['sortino_r']:.3f}")
    print(sep)
    print(f"  Mean MAE           : {s['mean_mae_r']:.3f}R  (worst adverse excursion)")
    print(f"  Mean MFE           : {s['mean_mfe_r']:.3f}R  (best favorable excursion)")
    print(f"  Hit rate @1.272    : {s['hit_rate_1272']:.1%}")
    print(f"  Hit rate @1.618    : {s['hit_rate_1618']:.1%}  (all trades, any exit)")
    print(sep)
    print(f"  CAGR (equity sim)  : {s['cagr']:.2%}")
    print(f"  Max drawdown       : {s['max_drawdown']:.2%}")
    print(f"  End equity         : ${s['end_equity']:,.0f}  (start ${s['start_equity']:,.0f})")
    print(f"  Avg bars held      : {s['avg_bars_held']:.1f}")
    print(sep)
    print(f"  Bullish trades     : {s['n_bullish_trades']}")
    print(f"  Bearish trades     : {s['n_bearish_trades']}")
    exit_str = "  ".join(f"{k}:{v}" for k, v in s["exit_reasons"].items())
    print(f"  Exit reasons       : {exit_str}")
    print(f"{'=' * 70}\n")


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------


def print_comparison_table(rows: list[dict]) -> None:
    if not rows:
        return
    print(f"\n{'=' * 110}")
    print(f"  FIB MODEL — COMPARISON TABLE")
    print(f"{'=' * 110}")
    hdr = (
        f"  {'Experiment':<30}  {'Ticker':<6}  {'Setups':>6}  {'ZoneHit':>7}  "
        f"{'Trades':>6}  {'WinR':>5}  {'ExpR':>6}  {'PF':>5}  "
        f"{'Shr':>5}  {'Hit1618':>7}  {'CAGR':>7}  {'MaxDD':>7}"
    )
    print(hdr)
    print("-" * 110)
    for r in rows:
        s = r["stats"]
        if s["n_trades"] == 0:
            print(
                f"  {r['exp']:<30}  {r['ticker']:<6}  {s['n_setups']:>6}  "
                f"{'N/A':>7}  {'0':>6}  {'—':>5}  {'—':>6}  {'—':>5}  {'—':>5}  {'—':>7}  {'—':>7}  {'—':>7}"
            )
            continue
        print(
            f"  {r['exp']:<30}  {r['ticker']:<6}  {s['n_setups']:>6}  "
            f"{s['zone_hit_rate']:>7.1%}  {s['n_trades']:>6}  "
            f"{s['win_rate']:>5.1%}  {s['expectancy_r']:>+6.3f}  "
            f"{s['profit_factor']:>5.2f}  {s['sharpe_r']:>5.3f}  "
            f"{s['hit_rate_1618']:>7.1%}  {s['cagr']:>7.2%}  {s['max_drawdown']:>7.2%}"
        )
    print(f"{'=' * 110}\n")


# ---------------------------------------------------------------------------
# Save results
# ---------------------------------------------------------------------------


def save_results(experiment_name: str, ticker: str, stats: dict) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    fname = f"{experiment_name}_{ticker}_{ts}.json"
    path = os.path.join(OUTPUT_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"experiment": experiment_name, "ticker": ticker, "stats": stats}, f, indent=2)
    return path


# ---------------------------------------------------------------------------
# Run one experiment / ticker combination
# ---------------------------------------------------------------------------


def run_one(
    experiment_name: str,
    ticker: str,
    config: FibModelConfig,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    bars = load_ticker(ticker, start_date=start_date, end_date=end_date)
    setups = find_manipulation_setups(bars, config)
    results = simulate(setups, bars, config)

    n_zone_hit = len(results)  # every result was a zone hit (sim only returns traded setups)
    stats = compute_stats(results, len(setups), n_zone_hit)
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fibonacci manipulation-leg model runner")
    p.add_argument(
        "--ticker", nargs="+", default=["SPY"], help="Ticker(s) to run against (default: SPY)"
    )
    p.add_argument(
        "--exp",
        nargs="+",
        default=list(FIB_EXPERIMENTS.keys()),
        help="Experiment name(s) to run (default: all)",
    )
    p.add_argument("--start", default=None, help="Start date YYYYMMDD")
    p.add_argument("--end", default=None, help="End date YYYYMMDD")
    p.add_argument("--list", action="store_true", help="List available experiments and exit")
    p.add_argument(
        "--save",
        action="store_true",
        default=True,
        help="Save JSON results to output/fib/ (default: True)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.list:
        print("Available fib experiments:")
        for name in list_fib_experiments():
            cfg = get_fib_config(name)
            print(
                f"  {name:<30}  dir={cfg.directions}  entry={cfg.entry_variant}"
                f"  target={cfg.target_fib}  pivot_n={cfg.pivot_n}"
            )
        return

    all_rows = []

    for exp_name in args.exp:
        config = get_fib_config(exp_name)
        for ticker in args.ticker:
            try:
                stats = run_one(exp_name, ticker, config, start_date=args.start, end_date=args.end)
            except FileNotFoundError as e:
                print(f"  SKIP {exp_name}/{ticker}: {e}")
                continue
            except Exception as e:
                print(f"  ERROR {exp_name}/{ticker}: {e}")
                import traceback

                traceback.print_exc()
                continue

            print_report(exp_name, ticker, stats, config)
            if args.save:
                path = save_results(exp_name, ticker, stats)
                print(f"  Saved: {path}")

            all_rows.append({"exp": exp_name, "ticker": ticker, "stats": stats})

    if len(all_rows) > 1:
        print_comparison_table(all_rows)


if __name__ == "__main__":
    main()
