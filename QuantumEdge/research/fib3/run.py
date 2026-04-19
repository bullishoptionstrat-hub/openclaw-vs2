"""
CLI runner for fib3 — leg quality gated Fibonacci model.

Usage (from QuantumEdge/ directory):
  python -m research.fib3.run
  python -m research.fib3.run --ticker SPY XLK
  python -m research.fib3.run --exp tier_D_broad tier_C tier_B tier_A
  python -m research.fib3.run --list
  python -m research.fib3.run --respect-only   # fib level respect table only

Key outputs:
  - Quality score distribution per tier (A/B/C/D) and leg count
  - Standard trade statistics per tier (win rate, ExpR, Sharpe, MaxDD, hit rates)
  - FIB LEVEL RESPECT TABLE: visit rate and reaction rate per level per tier
  - ATTRIBUTION: Pearson correlation of each quality component vs R multiple
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

from research.fib2.data import load_daily, load_hourly
from research.fib3.detector import find_qualified_legs
from research.fib3.backtester import simulate
from research.fib3.fib_respect import measure_leg_respect, aggregate_by_tier
from research.fib3.experiments import get_config, list_experiments, FIB3_EXPERIMENTS
from research.fib3.model import Fib3Config, QualifiedLeg
from research.fib3.analysis import (
    attribution_table,
    print_respect_table,
    print_attribution,
    print_tier_comparison,
)

OUTPUT_DIR = os.path.join(_QE_ROOT, "output", "fib3")


# ---------------------------------------------------------------------------
# Stats (same structure as fib2 for comparison)
# ---------------------------------------------------------------------------


def compute_stats(results, n_legs: int) -> dict:
    if not results:
        return {"n_legs": n_legs, "n_trades": 0, "zone_hit_rate": 0.0}

    n = len(results)
    r_vals = [t.r_multiple for t in results]
    wins = [t for t in results if t.r_multiple > 0]

    win_rate = len(wins) / n
    mean_r = sum(r_vals) / n
    med_r = sorted(r_vals)[n // 2]

    std_r = _std(r_vals)
    neg_r = [r for r in r_vals if r < 0]
    down_r = _std(neg_r) if neg_r else 1e-9
    sharpe = mean_r / std_r if std_r > 0 else 0.0
    sortino = mean_r / down_r if down_r > 0 else 0.0

    gw = sum(r for r in r_vals if r > 0)
    gl = abs(sum(r for r in r_vals if r < 0))
    pf = gw / gl if gl > 0 else float("inf")

    hit_1272 = sum(1 for t in results if t.reached_1272) / n
    hit_1618 = sum(1 for t in results if t.reached_1618) / n
    tout = sum(1 for t in results if t.exit_reason == "timeout") / n

    eq_vals = [results[0].equity_before] + [t.equity_after for t in results]
    bars = [t.entry_bar for t in results]
    cagr, max_dd = _equity_stats(eq_vals, bars)

    exit_reasons: dict[str, int] = {}
    for t in results:
        exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1

    return {
        "n_legs": n_legs,
        "n_trades": n,
        "zone_hit_rate": round(n / max(n_legs, 1), 4),
        "win_rate": round(win_rate, 4),
        "expectancy_r": round(mean_r, 4),
        "median_r": round(med_r, 4),
        "profit_factor": round(pf, 3),
        "sharpe_r": round(sharpe, 3),
        "sortino_r": round(sortino, 3),
        "mean_mae_r": round(sum(t.mae_r for t in results) / n, 4),
        "mean_mfe_r": round(sum(t.mfe_r for t in results) / n, 4),
        "hit_rate_1272": round(hit_1272, 4),
        "hit_rate_1618": round(hit_1618, 4),
        "timeout_rate": round(tout, 4),
        "cagr": round(cagr, 5),
        "max_drawdown": round(max_dd, 5),
        "avg_bars_held": round(sum(t.bars_held for t in results) / n, 1),
        "exit_reasons": exit_reasons,
        "start_equity": eq_vals[0],
        "end_equity": round(eq_vals[-1], 2),
    }


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 1e-9
    m = sum(vals) / len(vals)
    var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    return math.sqrt(max(var, 0))


def _equity_stats(eq_vals, bar_indices) -> tuple[float, float]:
    if len(eq_vals) < 2:
        return 0.0, 0.0
    s, e = eq_vals[0], eq_vals[-1]
    if bar_indices:
        years = max((bar_indices[-1] - bar_indices[0] + 1) / 252.0, 0.1)
    else:
        years = 1.0
    if s <= 0 or e <= 0:
        return 0.0, 0.0
    cagr = (e / s) ** (1.0 / years) - 1.0
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
# Quality distribution
# ---------------------------------------------------------------------------


def print_quality_dist(legs: list[QualifiedLeg], ticker: str) -> None:
    tiers = {"A": 0, "B": 0, "C": 0, "D": 0}
    scores = [l.quality.total for l in legs]
    for l in legs:
        tiers[l.quality.tier] += 1

    avg = sum(scores) / len(scores) if scores else 0.0
    print(f"\n  Leg quality distribution — {ticker}  (n={len(legs)})")
    print(
        f"    Tier A(>=75): {tiers['A']:3d}  "
        f"B(60-74): {tiers['B']:3d}  "
        f"C(40-59): {tiers['C']:3d}  "
        f"D(<40): {tiers['D']:3d}  "
        f"  avg_score={avg:.1f}"
    )

    # Component averages
    sw = sum(l.quality.sweep_score for l in legs) / max(len(legs), 1)
    di = sum(l.quality.displacement_score for l in legs) / max(len(legs), 1)
    ch = sum(l.quality.choch_score for l in legs) / max(len(legs), 1)
    ct = sum(l.quality.context_score for l in legs) / max(len(legs), 1)
    print(f"    Avg components - Sweep:{sw:.1f}  Disp:{di:.1f}  CHoCH:{ch:.1f}  Ctx:{ct:.1f}")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def print_report(exp_name: str, ticker: str, stats: dict, config: Fib3Config) -> None:
    s = stats
    sep = "-" * 72
    print(f"\n{'=' * 72}")
    print(f"  FIB3  |  exp={exp_name}  ticker={ticker}  Q>={config.quality_min_score:.0f}")
    print(f"{'=' * 72}")
    print(
        f"  Config: sweep={config.require_sweep}  disp_atr={config.min_displacement_atr}"
        f"  entry={config.entry_confirmation}  stop={config.stop_variant}"
        f"  target={config.target_fib}"
    )
    print(sep)
    print(f"  Legs detected      : {s['n_legs']}")
    print(f"  Trades executed    : {s['n_trades']}  (zone_hit={s['zone_hit_rate']:.1%})")
    if s["n_trades"] == 0:
        print("  No trades.")
        print(f"{'=' * 72}\n")
        return
    print(sep)
    print(f"  Win rate           : {s['win_rate']:.1%}")
    print(f"  Expectancy (R)     : {s['expectancy_r']:+.3f}R")
    print(f"  Profit factor      : {s['profit_factor']:.2f}")
    print(f"  Sharpe (on R)      : {s['sharpe_r']:.3f}")
    print(sep)
    print(f"  Hit rate @1.272    : {s['hit_rate_1272']:.1%}")
    print(f"  Hit rate @1.618    : {s['hit_rate_1618']:.1%}")
    print(f"  Timeout rate       : {s['timeout_rate']:.1%}")
    print(sep)
    print(f"  CAGR               : {s['cagr']:.2%}")
    print(f"  Max drawdown       : {s['max_drawdown']:.2%}")
    print(f"  Avg bars held      : {s['avg_bars_held']:.1f}")
    exit_str = "  ".join(f"{k}:{v}" for k, v in s["exit_reasons"].items())
    print(f"  Exit reasons       : {exit_str}")
    print(f"{'=' * 72}\n")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_one(
    exp_name: str,
    ticker: str,
    config: Fib3Config,
    start_date: str | None,
    end_date: str | None,
    spy_daily: dict | None,
    compute_respect: bool = True,
) -> tuple[dict, list[QualifiedLeg], list, list]:
    """
    Returns (stats, legs, results, respect_profiles).
    """
    daily = load_daily(ticker, start_date=start_date, end_date=end_date)

    legs = find_qualified_legs(
        daily,
        config,
        spy_daily=spy_daily if ticker != "SPY" else None,
    )
    results = simulate(
        legs,
        daily,
        config,
        spy_daily=spy_daily if ticker != "SPY" else None,
    )
    stats = compute_stats(results, len(legs))

    profiles = []
    if compute_respect and legs:
        for leg in legs:
            profiles.append(measure_leg_respect(leg, daily, config))

    return stats, legs, results, profiles


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
    p = argparse.ArgumentParser(description="fib3 leg-quality runner")
    p.add_argument("--ticker", nargs="+", default=["SPY"])
    p.add_argument("--exp", nargs="+", default=list(FIB3_EXPERIMENTS.keys()))
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--list", action="store_true")
    p.add_argument("--save", action="store_true", default=True)
    p.add_argument(
        "--respect-only",
        action="store_true",
        help="Print fib respect table only (no backtesting stats)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.list:
        print("Available fib3 experiments:")
        for name in list_experiments():
            cfg = get_config(name)
            print(
                f"  {name:<28}  Q≥{cfg.quality_min_score:.0f}"
                f"  sweep={cfg.require_sweep}  disp={cfg.min_displacement_atr}"
                f"  entry={cfg.entry_confirmation}"
            )
        return

    spy_daily: dict | None = None
    try:
        spy_daily = load_daily("SPY", start_date=args.start, end_date=args.end)
    except FileNotFoundError:
        pass

    # For the respect analysis, run ALL tiers on a single ticker first so
    # we can compare them in the same table.
    # Group experiments by ticker so we can print one respect table per ticker.
    tier_exps = ["tier_D_broad", "tier_C", "tier_B", "tier_A"]
    all_rows = []

    for ticker in args.ticker:
        # ── Quality distribution (always run tier_D_broad as base) ──────────
        try:
            base_cfg = get_config("tier_D_broad")
            base_cfg.start_date = args.start  # ignored by load, but for ref
            daily = load_daily(ticker, start_date=args.start, end_date=args.end)
            all_legs = find_qualified_legs(
                daily,
                base_cfg,
                spy_daily=spy_daily if ticker != "SPY" else None,
            )
            print_quality_dist(all_legs, ticker)

            # ── Fib respect analysis across tiers (one table per ticker) ────
            profiles = [measure_leg_respect(l, daily, base_cfg) for l in all_legs]
            tier_aggregate = aggregate_by_tier(profiles)
            print_respect_table(tier_aggregate, ticker)

        except FileNotFoundError as e:
            print(f"  SKIP quality dist {ticker}: {e}")
            all_legs = []
            tier_aggregate = {}

        if args.respect_only:
            continue

        # ── Per-experiment backtesting ───────────────────────────────────────
        for exp_name in args.exp:
            config = get_config(exp_name)
            try:
                stats, legs, results, _ = run_one(
                    exp_name,
                    ticker,
                    config,
                    start_date=args.start,
                    end_date=args.end,
                    spy_daily=spy_daily,
                    compute_respect=False,  # Already computed above
                )
            except FileNotFoundError as e:
                print(f"  SKIP {exp_name}/{ticker}: {e}")
                continue
            except Exception as e:
                import traceback

                print(f"  ERROR {exp_name}/{ticker}: {e}")
                traceback.print_exc()
                continue

            print_report(exp_name, ticker, stats, config)

            # Attribution (only if we have both results and legs)
            if results and legs:
                legs_by_db = {l.discovery_bar: l for l in legs}
                attr = attribution_table(results, legs_by_db)
                print_attribution(attr, ticker, exp_name)

            if args.save:
                path = save_results(exp_name, ticker, stats)
                print(f"  Saved: {path}")

            all_rows.append({"exp": exp_name, "ticker": ticker, "stats": stats})

    if len(all_rows) > 1:
        print_tier_comparison(all_rows)


if __name__ == "__main__":
    main()
