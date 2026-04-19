"""
CLI runner for fib4 — execution-focused Fibonacci model.

Usage (from QuantumEdge/ directory):
  python -m research.fib4.run
  python -m research.fib4.run --ticker SPY XLK QQQ
  python -m research.fib4.run --exp spy_tierA_touch_rejection spy_tierA_1h_confirm
  python -m research.fib4.run --mandatory        # Run the 8 mandatory experiments
  python -m research.fib4.run --list

Outputs:
  1. Per-experiment trade statistics with skip rate + trigger breakdown
  2. Grand comparison table (execution variants vs fib3 baselines)
  3. Verdict: did execution precision unlock the edge?
  4. Strategy role recommendation

Note: For SPY, 1H data is loaded automatically if available.
      For XLK and QQQ, 1H triggers fall back to daily (as configured).
"""

from __future__ import annotations

import sys
import os
import json
import argparse
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_QE_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _QE_ROOT not in sys.path:
    sys.path.insert(0, _QE_ROOT)

from research.fib2.data import load_daily, load_hourly, build_date_to_1h_range
from research.fib3.detector import find_qualified_legs
from research.fib4.backtester import simulate
from research.fib4.experiments import (
    get_config,
    list_experiments,
    FIB4_EXPERIMENTS,
    MANDATORY_EXPERIMENTS,
    BASELINE_EXPERIMENTS,
)
from research.fib4.analysis import (
    compute_stats,
    print_report,
    print_comparison_table,
    print_verdict,
)

OUTPUT_DIR = os.path.join(_QE_ROOT, "output", "fib4")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_one(
    exp_name: str,
    ticker: str,
    start_date,
    end_date,
    spy_daily,
    hourly_bars=None,
    date_to_1h=None,
    verbose: bool = True,
):
    """
    Load data, detect legs, simulate, return (stats, results).
    """
    config = get_config(exp_name)

    daily = load_daily(ticker, start_date=start_date, end_date=end_date)

    # Detect legs using fib3 detector with quality scoring
    legs = find_qualified_legs(
        daily,
        config,
        spy_daily=spy_daily if ticker != "SPY" else None,
    )

    # Simulate with fib4 execution engine
    results, n_legs, n_skipped = simulate(
        legs,
        daily,
        config,
        hourly_bars=hourly_bars,
        date_to_1h=date_to_1h,
        spy_daily=spy_daily if ticker != "SPY" else None,
    )

    stats = compute_stats(results, n_legs, n_skipped)

    if verbose:
        print_report(exp_name, ticker, stats, config)

    return stats, results


def save_results(exp_name: str, ticker: str, stats: dict) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    fname = f"{exp_name}_{ticker}_{ts}.json"
    path = os.path.join(OUTPUT_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"experiment": exp_name, "ticker": ticker, "stats": stats}, f, indent=2)
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="fib4 execution research runner")
    p.add_argument("--ticker", nargs="+", default=["SPY", "XLK", "QQQ"])
    p.add_argument("--exp", nargs="+", default=None)
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--list", action="store_true")
    p.add_argument(
        "--mandatory",
        action="store_true",
        help="Run only the 8 mandatory first experiments + baselines",
    )
    p.add_argument("--save", action="store_true", default=True)
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.list:
        print("Available fib4 experiments:")
        for name in list_experiments():
            cfg = get_config(name)
            print(
                f"  {name:<32}  Q>={cfg.quality_min_score:.0f}"
                f"  sweep_min={cfg.quality_min_sweep:.0f}"
                f"  trigger={cfg.entry_trigger}"
            )
        return

    # ── Load SPY data once (used as regime filter for other tickers) ──────────
    spy_daily = None
    try:
        spy_daily = load_daily("SPY", start_date=args.start, end_date=args.end)
    except FileNotFoundError:
        pass

    # ── Load hourly data for SPY (1H triggers) ────────────────────────────────
    spy_hourly = None
    spy_date_to_1h = None
    if spy_daily is not None:
        spy_hourly = load_hourly("SPY", start_date=args.start, end_date=args.end)
        if spy_hourly is not None and spy_daily is not None:
            spy_date_to_1h = build_date_to_1h_range(spy_daily, spy_hourly)

    # ── Determine which experiments to run ───────────────────────────────────
    if args.mandatory:
        run_pairs = BASELINE_EXPERIMENTS + MANDATORY_EXPERIMENTS
    elif args.exp:
        # User-specified experiments; need to figure out tickers
        # Determine ticker from experiment name prefix
        run_pairs = []
        for exp_name in args.exp:
            for ticker in args.ticker:
                pfx = ticker.lower()
                if exp_name.startswith(pfx + "_"):
                    run_pairs.append((exp_name, ticker.upper()))
                    break
            else:
                # Default: run against all specified tickers
                for ticker in args.ticker:
                    run_pairs.append((exp_name, ticker.upper()))
    else:
        # Default: run baselines + all experiments matching requested tickers
        run_pairs = []
        for ticker in args.ticker:
            pfx = ticker.lower()
            # baselines first
            for exp_name, exp_ticker in BASELINE_EXPERIMENTS:
                if exp_ticker.upper() == ticker.upper():
                    run_pairs.append((exp_name, exp_ticker))
            # then all matching experiments
            for exp_name in list_experiments():
                if exp_name.startswith(pfx + "_") and not exp_name.endswith("_baseline"):
                    run_pairs.append((exp_name, ticker.upper()))

    # ── Print header ────────────────────────────────────────────────────────
    print(f"\n{'#' * 76}")
    print("  FIB4: Execution-Focused Fibonacci Research Module")
    print(f"{'#' * 76}")
    print(f"  Tickers        : {', '.join(args.ticker)}")
    print(f"  Experiments    : {len(run_pairs)}")
    print(f"  Date range     : {args.start or 'all'} -> {args.end or 'all'}")
    print(f"  SPY 1H data    : {'loaded' if spy_hourly else 'not available'}")
    print()

    # ── Run experiments ────────────────────────────────────────────────────
    all_rows = []

    for exp_name, ticker in run_pairs:
        if exp_name not in FIB4_EXPERIMENTS:
            print(f"  SKIP: unknown experiment '{exp_name}'")
            continue

        # Select hourly data (only SPY has it)
        h_bars = spy_hourly if ticker == "SPY" else None
        d_to_1h = spy_date_to_1h if ticker == "SPY" else None

        try:
            stats, results = run_one(
                exp_name,
                ticker,
                start_date=args.start,
                end_date=args.end,
                spy_daily=spy_daily,
                hourly_bars=h_bars,
                date_to_1h=d_to_1h,
                verbose=True,
            )
        except FileNotFoundError as exc:
            print(f"  SKIP {exp_name}/{ticker}: {exc}")
            continue
        except Exception as exc:
            import traceback

            print(f"  ERROR {exp_name}/{ticker}: {exc}")
            traceback.print_exc()
            continue

        all_rows.append({"exp": exp_name, "ticker": ticker, "stats": stats})

        if args.save:
            path = save_results(exp_name, ticker, stats)
            print(f"  Saved: {path}")

    # ── Grand comparison table ─────────────────────────────────────────────
    if len(all_rows) > 1:
        # Sort: baselines first per ticker, then other experiments
        baseline_rows = [r for r in all_rows if r["exp"].endswith("_baseline")]
        non_baseline = [r for r in all_rows if not r["exp"].endswith("_baseline")]
        ordered = baseline_rows + non_baseline
        print_comparison_table(ordered)
        print_verdict(ordered)


if __name__ == "__main__":
    main()
