"""
CLI runner for fib5 — robustness, replication, and portfolio role validation.

Usage (from QuantumEdge/ directory):
  python -m research.fib5.run                  # Full mandatory run
  python -m research.fib5.run --track 1        # Replication only
  python -m research.fib5.run --track 2        # OOS only
  python -m research.fib5.run --track 3        # Robustness only
  python -m research.fib5.run --track 4        # Friction only
  python -m research.fib5.run --track 5        # Regime decomposition only
  python -m research.fib5.run --ticker XLK QQQ # Override tickers

Mandatory first run (--mandatory or default):
  Track 1: Replication on tech/growth + sector ETFs
  Track 2: IS/OOS split on XLK, QQQ, SPY
  Track 3: Robustness grid on XLK and QQQ winner configs
  Track 4: Friction-adjusted reruns on XLK and QQQ
  Track 5: Regime decomposition on XLK and QQQ
"""

from __future__ import annotations

import sys
import os
import argparse

_HERE = os.path.dirname(os.path.abspath(__file__))
_QE_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _QE_ROOT not in sys.path:
    sys.path.insert(0, _QE_ROOT)

from research.fib2.data import load_daily, load_hourly, build_date_to_1h_range
from research.fib3.detector import find_qualified_legs
from research.fib5.backtester import simulate, friction_adjusted_r
from research.fib5.walkforward import run_oos_batch, run_period
from research.fib5.robustness import build_xlk_grid, build_qqq_grid, run_grid, summarize_grid
from research.fib5.regime import decompose_results
from research.fib5.experiments import (
    get_strategies,
    ALL_REPLICATION_TICKERS,
    OOS_TICKERS,
    SLIPPAGE_REALISTIC,
    SLIPPAGE_CONSERVATIVE,
    make_xlk_style,
    make_qqq_style,
)
from research.fib5.analysis import (
    compute_stats,
    compute_stats_from_r,
    print_replication_table,
    print_oos_table,
    print_robustness_table,
    print_friction_table,
    print_regime_table,
    print_final_verdict,
)


# ---------------------------------------------------------------------------
# Track runners
# ---------------------------------------------------------------------------


def track1_replication(tickers, strategies, spy_daily, spy_hourly, spy_d_to_1h):
    """Run all strategies on all tickers, return rows for comparison table."""
    print(f"\n{'=' * 76}")
    print("  TRACK 1: REPLICATION")
    print(f"{'=' * 76}")
    rows = []
    for strat_name, config in strategies.items():
        for ticker in tickers:
            h_bars = spy_hourly if ticker == "SPY" else None
            d_to_1h = spy_d_to_1h if ticker == "SPY" else None
            try:
                daily = load_daily(ticker)
            except FileNotFoundError:
                print(f"  SKIP {ticker}: not in dataset")
                continue

            legs = find_qualified_legs(
                daily, config, spy_daily=spy_daily if ticker != "SPY" else None
            )
            results, n_legs, n_skipped = simulate(
                legs,
                daily,
                config,
                hourly_bars=h_bars,
                date_to_1h=d_to_1h,
                spy_daily=spy_daily if ticker != "SPY" else None,
            )
            stats = compute_stats(results, n_legs, n_skipped)
            rows.append({"strategy": strat_name, "ticker": ticker, "stats": stats})
    return rows


def track2_oos(oos_tickers, strategies, spy_daily, spy_hourly, spy_d_to_1h):
    """IS/OOS split on key tickers."""
    print(f"\n{'=' * 76}")
    print("  TRACK 2: OUT-OF-SAMPLE SPLITS")
    print(f"{'=' * 76}")

    # Only run xlk_style, qqq_style, spy_style for OOS (skip baseline)
    oos_strategies = {
        k: v for k, v in strategies.items() if k in ("xlk_style", "qqq_style", "spy_style")
    }
    return run_oos_batch(
        oos_strategies,
        oos_tickers,
        spy_daily,
        spy_hourly=spy_hourly,
        spy_date_to_1h=spy_d_to_1h,
    )


def track3_robustness(spy_daily):
    """Parameter grid for XLK and QQQ winners."""
    print(f"\n{'=' * 76}")
    print("  TRACK 3: PARAMETER ROBUSTNESS")
    print(f"{'=' * 76}")
    print("  Building XLK grid (36 configs)...")
    xlk_grid = run_grid(build_xlk_grid(), "XLK", None, None, spy_daily)
    xlk_summary = summarize_grid(xlk_grid)

    print("  Building QQQ grid (36 configs)...")
    qqq_grid = run_grid(build_qqq_grid(), "QQQ", None, None, spy_daily)
    qqq_summary = summarize_grid(qqq_grid)

    return xlk_grid, xlk_summary, qqq_grid, qqq_summary


def track4_friction(spy_daily, tickers=None):
    """Friction-adjusted reruns for XLK and QQQ."""
    print(f"\n{'=' * 76}")
    print("  TRACK 4: FRICTION ADJUSTMENT")
    print(f"{'=' * 76}")
    if tickers is None:
        tickers = ["XLK", "QQQ", "SPY", "IWM"]

    friction_rows = []
    configs_by_strat = {
        "xlk_style": make_xlk_style(slippage_pct=0.0),
        "qqq_style": make_qqq_style(slippage_pct=0.0),
    }
    for strat_name, base_cfg in configs_by_strat.items():
        for ticker in tickers:
            try:
                daily = load_daily(ticker)
            except FileNotFoundError:
                continue

            legs = find_qualified_legs(
                daily, base_cfg, spy_daily=spy_daily if ticker != "SPY" else None
            )
            results, n_legs, n_skipped = simulate(
                legs,
                daily,
                base_cfg,
                spy_daily=spy_daily if ticker != "SPY" else None,
            )
            if not results:
                friction_rows.append(
                    {
                        "strategy": strat_name,
                        "ticker": ticker,
                        "n_trades": 0,
                        "raw_exp_r": 0.0,
                        "adj_exp_r_5bps": 0.0,
                        "adj_exp_r_10bps": 0.0,
                    }
                )
                continue

            raw_r = [t.r_multiple for t in results]
            raw_exp = sum(raw_r) / len(raw_r)

            # 5bps slippage
            cfg5 = (
                make_xlk_style(slippage_pct=SLIPPAGE_REALISTIC)
                if strat_name == "xlk_style"
                else make_qqq_style(slippage_pct=SLIPPAGE_REALISTIC)
            )
            adj5 = friction_adjusted_r(results, cfg5)
            exp5 = sum(adj5) / len(adj5)

            # 10bps slippage
            cfg10 = (
                make_xlk_style(slippage_pct=SLIPPAGE_CONSERVATIVE)
                if strat_name == "xlk_style"
                else make_qqq_style(slippage_pct=SLIPPAGE_CONSERVATIVE)
            )
            adj10 = friction_adjusted_r(results, cfg10)
            exp10 = sum(adj10) / len(adj10)

            friction_rows.append(
                {
                    "strategy": strat_name,
                    "ticker": ticker,
                    "n_trades": len(results),
                    "raw_exp_r": round(raw_exp, 4),
                    "adj_exp_r_5bps": round(exp5, 4),
                    "adj_exp_r_10bps": round(exp10, 4),
                }
            )
    return friction_rows


def track5_regime(spy_daily, focus_tickers=None):
    """Regime decomposition for XLK and QQQ winners."""
    print(f"\n{'=' * 76}")
    print("  TRACK 5: REGIME DECOMPOSITION")
    print(f"{'=' * 76}")
    if focus_tickers is None:
        focus_tickers = ["XLK", "QQQ", "SPY"]

    configs_by_strat = {
        "xlk_style": make_xlk_style(),
        "qqq_style": make_qqq_style(),
    }
    for strat_name, config in configs_by_strat.items():
        for ticker in focus_tickers:
            try:
                daily = load_daily(ticker)
            except FileNotFoundError:
                continue

            legs = find_qualified_legs(
                daily, config, spy_daily=spy_daily if ticker != "SPY" else None
            )
            results, _, _ = simulate(
                legs,
                daily,
                config,
                spy_daily=spy_daily if ticker != "SPY" else None,
            )
            if results:
                decomp = decompose_results(results)
                print_regime_table(decomp, strat_name, ticker)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args():
    p = argparse.ArgumentParser(description="fib5 robustness and replication runner")
    p.add_argument(
        "--track",
        type=int,
        nargs="+",
        default=None,
        help="Run specific track(s): 1=replication, 2=OOS, 3=robustness, 4=friction, 5=regime",
    )
    p.add_argument("--ticker", nargs="+", default=None)
    p.add_argument("--mandatory", action="store_true")
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    return p.parse_args()


def main():
    args = parse_args()

    # ── Load SPY data once ────────────────────────────────────────────────────
    spy_daily = None
    try:
        spy_daily = load_daily("SPY")
    except FileNotFoundError:
        print("  WARNING: SPY daily data not found")

    spy_hourly = None
    spy_d_to_1h = None
    if spy_daily is not None:
        spy_hourly = load_hourly("SPY")
        if spy_hourly is not None:
            spy_d_to_1h = build_date_to_1h_range(spy_daily, spy_hourly)

    # ── Determine which tracks to run ─────────────────────────────────────────
    if args.track:
        tracks = set(args.track)
    else:
        tracks = {1, 2, 3, 4, 5}  # All tracks

    # ── Instrument sets ───────────────────────────────────────────────────────
    if args.ticker:
        rep_tickers = [t.upper() for t in args.ticker]
        oos_tickers = rep_tickers
    else:
        rep_tickers = ALL_REPLICATION_TICKERS
        oos_tickers = OOS_TICKERS

    # Base strategies (no friction)
    strategies = get_strategies(with_friction=False)

    print(f"\n{'#' * 76}")
    print("  FIB5: Robustness, Replication, and Portfolio Role Validation")
    print(f"{'#' * 76}")
    print(f"  Replication tickers : {', '.join(rep_tickers)}")
    print(f"  OOS tickers         : {', '.join(oos_tickers)}")
    print(f"  Tracks              : {sorted(tracks)}")
    print(f"  SPY 1H data         : {'loaded' if spy_hourly else 'not available'}")

    replication_rows = []
    oos_splits = []
    xlk_grid, xlk_summary, qqq_grid, qqq_summary = [], {}, [], {}
    friction_rows = []

    # ── Track 1: Replication ─────────────────────────────────────────────────
    if 1 in tracks:
        replication_rows = track1_replication(
            rep_tickers, strategies, spy_daily, spy_hourly, spy_d_to_1h
        )
        print_replication_table(replication_rows)

    # ── Track 2: OOS ─────────────────────────────────────────────────────────
    if 2 in tracks:
        oos_splits = track2_oos(oos_tickers, strategies, spy_daily, spy_hourly, spy_d_to_1h)
        print_oos_table(oos_splits)

    # ── Track 3: Robustness ───────────────────────────────────────────────────
    if 3 in tracks:
        xlk_grid, xlk_summary, qqq_grid, qqq_summary = track3_robustness(spy_daily)
        print_robustness_table(xlk_summary, qqq_summary, xlk_grid, qqq_grid)

    # ── Track 4: Friction ─────────────────────────────────────────────────────
    if 4 in tracks:
        friction_rows = track4_friction(spy_daily, tickers=oos_tickers)
        print_friction_table(friction_rows)

    # ── Track 5: Regime ───────────────────────────────────────────────────────
    if 5 in tracks:
        track5_regime(spy_daily, focus_tickers=["XLK", "QQQ", "SPY"])

    # ── Final Verdict ─────────────────────────────────────────────────────────
    if tracks == {1, 2, 3, 4, 5} or args.mandatory:
        print_final_verdict(
            replication_rows,
            oos_splits,
            xlk_summary,
            qqq_summary,
            friction_rows,
        )


if __name__ == "__main__":
    main()
