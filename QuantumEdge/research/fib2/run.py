"""
CLI runner for the fib2 strict manipulation-leg model.

Usage (from QuantumEdge/ directory):
  python -m research.fib2.run                          # all experiments, SPY
  python -m research.fib2.run --ticker SPY QQQ XLK     # multiple tickers
  python -m research.fib2.run --exp strict_baseline broad_fib1_equiv
  python -m research.fib2.run --list
  python -m research.fib2.run --start 20150101 --end 20221231

Key outputs per run:
  - sample size, win rate, expectancy, PF, Sharpe, MaxDD
  - hit rates @1.272 and @1.618
  - timeout rate
  - MAE / MFE
  - regime breakdown (bull vs bear regime)
  - direction breakdown
  - strict vs broad direct comparison when both are in --exp
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

from research.fib2.data import load_daily, load_hourly, build_date_to_1h_range
from research.fib2.detector import find_strict_legs
from research.fib2.backtester import simulate
from research.fib2.experiments import get_config, list_experiments, FIB2_EXPERIMENTS
from research.fib2.model import StrictFibConfig, StrictTradeResult

OUTPUT_DIR = os.path.join(_QE_ROOT, "output", "fib2")


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def compute_stats(results: list[StrictTradeResult], n_legs: int) -> dict:
    n_zone_wait = n_legs  # All legs were evaluated; 'traded' = entered zone
    if not results:
        return {
            "n_legs": n_legs,
            "n_trades": 0,
            "zone_hit_rate": 0.0,
        }

    n = len(results)
    r_vals = [t.r_multiple for t in results]
    wins = [t for t in results if t.is_winner()]

    win_rate = len(wins) / n
    mean_r = sum(r_vals) / n
    med_r = sorted(r_vals)[n // 2]

    std_r = _std(r_vals)
    neg_r = [r for r in r_vals if r < 0]
    down_r = _std(neg_r) if neg_r else 1e-9
    sharpe = mean_r / std_r if std_r > 0 else 0.0
    sortino = mean_r / down_r if down_r > 0 else 0.0

    gross_win = sum(r for r in r_vals if r > 0)
    gross_loss = abs(sum(r for r in r_vals if r < 0))
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")

    mae_vals = [t.mae_r for t in results]
    mfe_vals = [t.mfe_r for t in results]

    hit_1272 = sum(1 for t in results if t.reached_1272) / n
    hit_1618 = sum(1 for t in results if t.reached_1618) / n
    timeout_rate = sum(1 for t in results if t.exit_reason == "timeout") / n

    eq_vals = [results[0].equity_before] + [t.equity_after for t in results]
    bars = [t.entry_bar for t in results]
    cagr, max_dd = _equity_stats(eq_vals, bars)

    avg_bars = sum(t.bars_held for t in results) / n

    exit_reasons: dict[str, int] = {}
    for t in results:
        exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1

    dir_bull = [t for t in results if t.leg.direction == "bullish"]
    dir_bear = [t for t in results if t.leg.direction == "bearish"]

    # Regime breakdown
    bull_reg = [t for t in results if t.spy_bull_regime]
    bear_reg = [t for t in results if not t.spy_bull_regime]

    def _sub_stats(sub: list) -> dict:
        if not sub:
            return {"n": 0, "win_rate": None, "expectancy_r": None}
        sr = [t.r_multiple for t in sub]
        return {
            "n": len(sub),
            "win_rate": round(sum(1 for r in sr if r > 0) / len(sr), 4),
            "expectancy_r": round(sum(sr) / len(sr), 4),
        }

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
        "mean_mae_r": round(sum(mae_vals) / n, 4),
        "mean_mfe_r": round(sum(mfe_vals) / n, 4),
        "hit_rate_1272": round(hit_1272, 4),
        "hit_rate_1618": round(hit_1618, 4),
        "timeout_rate": round(timeout_rate, 4),
        "cagr": round(cagr, 5),
        "max_drawdown": round(max_dd, 5),
        "avg_bars_held": round(avg_bars, 1),
        "exit_reasons": exit_reasons,
        "n_bullish_trades": len(dir_bull),
        "n_bearish_trades": len(dir_bear),
        "bullish_stats": _sub_stats(dir_bull),
        "bearish_stats": _sub_stats(dir_bear),
        "spy_bull_regime_stats": _sub_stats(bull_reg),
        "spy_bear_regime_stats": _sub_stats(bear_reg),
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
    if len(eq_vals) < 2:
        return 0.0, 0.0
    start_eq, end_eq = eq_vals[0], eq_vals[-1]
    if bar_indices:
        years = max((bar_indices[-1] - bar_indices[0] + 1) / 252.0, 0.1)
    else:
        years = 1.0
    if start_eq <= 0 or end_eq <= 0:
        return 0.0, 0.0
    cagr = (end_eq / start_eq) ** (1.0 / years) - 1.0
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
# Report
# ---------------------------------------------------------------------------


def print_report(exp_name: str, ticker: str, stats: dict, config: StrictFibConfig) -> None:
    s = stats
    sep = "-" * 72
    print(f"\n{'=' * 72}")
    print(f"  FIB2 STRICT MODEL  |  exp={exp_name}  ticker={ticker}")
    print(f"{'=' * 72}")
    print(
        f"  Config: sweep={config.require_sweep}  disp_atr={config.min_displacement_atr}"
        f"  entry={config.entry_confirmation}  stop={config.stop_variant}"
        f"  target={config.target_fib}  pivot_n={config.pivot_n}"
    )
    print(sep)
    print(f"  Legs detected      : {s['n_legs']}")
    print(f"  Trades executed    : {s['n_trades']}  (zone_hit={s['zone_hit_rate']:.1%})")
    if s["n_trades"] == 0:
        print("  No trades — filters too strict or insufficient data.")
        print(f"{'=' * 72}\n")
        return
    print(sep)
    print(f"  Win rate           : {s['win_rate']:.1%}")
    print(f"  Expectancy (R)     : {s['expectancy_r']:+.3f}R")
    print(f"  Median R           : {s['median_r']:+.3f}R")
    print(f"  Profit factor      : {s['profit_factor']:.2f}")
    print(f"  Sharpe (on R)      : {s['sharpe_r']:.3f}")
    print(f"  Sortino (on R)     : {s['sortino_r']:.3f}")
    print(sep)
    print(f"  Mean MAE           : {s['mean_mae_r']:.3f}R")
    print(f"  Mean MFE           : {s['mean_mfe_r']:.3f}R")
    print(f"  Hit rate @1.272    : {s['hit_rate_1272']:.1%}")
    print(f"  Hit rate @1.618    : {s['hit_rate_1618']:.1%}")
    print(f"  Timeout rate       : {s['timeout_rate']:.1%}")
    print(sep)
    print(f"  CAGR               : {s['cagr']:.2%}")
    print(f"  Max drawdown       : {s['max_drawdown']:.2%}")
    print(f"  End equity         : ${s['end_equity']:,.0f}  (start ${s['start_equity']:,.0f})")
    print(f"  Avg bars held      : {s['avg_bars_held']:.1f}")
    print(sep)
    print(f"  Bullish trades     : {s['n_bullish_trades']}")
    print(f"  Bearish trades     : {s['n_bearish_trades']}")
    bs = s["bullish_stats"]
    if bs["n"] > 0:
        print(f"    Bull: WinR={bs['win_rate']:.1%}  ExpR={bs['expectancy_r']:+.3f}R  n={bs['n']}")
    bear_s = s["bearish_stats"]
    if bear_s["n"] > 0:
        print(
            f"    Bear: WinR={bear_s['win_rate']:.1%}  ExpR={bear_s['expectancy_r']:+.3f}R  n={bear_s['n']}"
        )
    print(sep)
    sr = s["spy_bull_regime_stats"]
    br = s["spy_bear_regime_stats"]
    if sr["n"] > 0:
        print(
            f"  Spy BULL regime    : n={sr['n']}  WinR={sr['win_rate']:.1%}  ExpR={sr['expectancy_r']:+.3f}R"
        )
    if br["n"] > 0:
        print(
            f"  Spy BEAR regime    : n={br['n']}  WinR={br['win_rate']:.1%}  ExpR={br['expectancy_r']:+.3f}R"
        )
    exit_str = "  ".join(f"{k}:{v}" for k, v in s["exit_reasons"].items())
    print(f"  Exit reasons       : {exit_str}")
    print(f"{'=' * 72}\n")


def print_comparison_table(rows: list[dict]) -> None:
    if not rows:
        return
    print(f"\n{'=' * 118}")
    print(f"  FIB2 STRICT MODEL -- COMPARISON TABLE")
    print(f"{'=' * 118}")
    hdr = (
        f"  {'Experiment':<28}  {'Ticker':<5}  {'Legs':>5}  {'Trades':>6}  "
        f"{'WinR':>5}  {'ExpR':>6}  {'PF':>5}  {'Shr':>5}  "
        f"{'Hit1272':>7}  {'Hit1618':>7}  {'Tout':>5}  {'CAGR':>7}  {'MaxDD':>7}"
    )
    print(hdr)
    print("-" * 118)
    for r in rows:
        s = r["stats"]
        if s["n_trades"] == 0:
            print(
                f"  {r['exp']:<28}  {r['ticker']:<5}  {s['n_legs']:>5}  "
                f"{'0':>6}  {'--':>5}  {'--':>6}  {'--':>5}  {'--':>5}  "
                f"{'--':>7}  {'--':>7}  {'--':>5}  {'--':>7}  {'--':>7}"
            )
            continue
        print(
            f"  {r['exp']:<28}  {r['ticker']:<5}  {s['n_legs']:>5}  "
            f"{s['n_trades']:>6}  {s['win_rate']:>5.1%}  {s['expectancy_r']:>+6.3f}  "
            f"{s['profit_factor']:>5.2f}  {s['sharpe_r']:>5.3f}  "
            f"{s['hit_rate_1272']:>7.1%}  {s['hit_rate_1618']:>7.1%}  "
            f"{s['timeout_rate']:>5.1%}  {s['cagr']:>7.2%}  {s['max_drawdown']:>7.2%}"
        )
    print(f"{'=' * 118}\n")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_one(
    exp_name: str,
    ticker: str,
    config: StrictFibConfig,
    start_date: str | None = None,
    end_date: str | None = None,
    spy_daily: dict | None = None,
) -> dict:
    daily = load_daily(ticker, start_date=start_date, end_date=end_date)
    hourly = load_hourly(ticker, start_date=start_date, end_date=end_date)
    date_to_1h = build_date_to_1h_range(daily, hourly) if hourly else None

    legs = find_strict_legs(daily, config)
    results = simulate(
        legs,
        daily,
        config,
        hourly_bars=hourly,
        date_to_1h=date_to_1h,
        spy_daily=spy_daily,
    )

    stats = compute_stats(results, len(legs))
    return stats


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
    p = argparse.ArgumentParser(description="fib2 strict model runner")
    p.add_argument("--ticker", nargs="+", default=["SPY"])
    p.add_argument("--exp", nargs="+", default=list(FIB2_EXPERIMENTS.keys()))
    p.add_argument("--start", default=None, help="YYYYMMDD")
    p.add_argument("--end", default=None, help="YYYYMMDD")
    p.add_argument("--list", action="store_true")
    p.add_argument("--save", action="store_true", default=True)
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.list:
        print("Available fib2 experiments:")
        for name in list_experiments():
            cfg = get_config(name)
            print(
                f"  {name:<30}  sweep={cfg.require_sweep}  disp={cfg.min_displacement_atr}"
                f"  entry={cfg.entry_confirmation}  stop={cfg.stop_variant}"
                f"  target={cfg.target_fib}"
            )
        return

    # Pre-load SPY daily for regime filter (used across all tickers)
    spy_daily: dict | None = None
    try:
        spy_daily = load_daily("SPY")
    except FileNotFoundError:
        pass

    all_rows = []

    for exp_name in args.exp:
        config = get_config(exp_name)
        for ticker in args.ticker:
            try:
                stats = run_one(
                    exp_name,
                    ticker,
                    config,
                    start_date=args.start,
                    end_date=args.end,
                    spy_daily=spy_daily if ticker != "SPY" else None,
                )
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
