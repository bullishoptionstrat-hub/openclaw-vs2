"""
fib4 analysis helpers.

Extends fib3 analysis with:
  - skip rate tracking (n_skipped / n_legs)
  - trigger type breakdown (which trigger fired most)
  - execution delta vs baseline (how much did execution precision help)
  - final verdict logic
"""

from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def compute_stats(results: list, n_legs: int, n_skipped: int) -> dict:
    """
    Extended stats including skip tracking and trigger breakdown.
    """
    if not results:
        return {
            "n_legs": n_legs,
            "n_trades": 0,
            "n_skipped": n_skipped,
            "skip_rate": round(n_skipped / max(n_legs, 1), 4),
            "zone_hit_rate": 0.0,
        }

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

    gw = sum(r for r in r_vals if r > 0)
    gl = abs(sum(r for r in r_vals if r < 0))
    pf = gw / gl if gl > 0 else float("inf")

    hit_1272 = sum(1 for t in results if t.reached_1272) / n
    hit_1618 = sum(1 for t in results if t.reached_1618) / n
    tout = sum(1 for t in results if t.exit_reason == "timeout") / n

    # Trigger breakdown
    trigger_counts: dict[str, int] = {}
    for t in results:
        key = t.entry_confirmation_type
        trigger_counts[key] = trigger_counts.get(key, 0) + 1

    # Trigger-level win rates
    trigger_wins: dict[str, int] = {}
    trigger_r: dict[str, list] = {}
    for t in results:
        key = t.entry_confirmation_type
        if key not in trigger_wins:
            trigger_wins[key] = 0
            trigger_r[key] = []
        if t.r_multiple > 0:
            trigger_wins[key] += 1
        trigger_r[key].append(t.r_multiple)

    trigger_stats = {}
    for key in trigger_counts:
        cnt = trigger_counts[key]
        w = trigger_wins.get(key, 0)
        rs = trigger_r.get(key, [])
        trigger_stats[key] = {
            "n": cnt,
            "win_rate": round(w / cnt, 4),
            "avg_r": round(sum(rs) / len(rs), 4) if rs else 0.0,
        }

    eq_vals = [results[0].equity_before] + [t.equity_after for t in results]
    bar_idx = [t.entry_bar for t in results]
    cagr, max_dd = _equity_stats(eq_vals, bar_idx)

    exit_reasons: dict[str, int] = {}
    for t in results:
        exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1

    return {
        "n_legs": n_legs,
        "n_trades": n,
        "n_skipped": n_skipped,
        "skip_rate": round(n_skipped / max(n_legs, 1), 4),
        "zone_hit_rate": round(n / max(n_legs, 1), 4),
        "win_rate": round(win_rate, 4),
        "expectancy_r": round(mean_r, 4),
        "median_r": round(med_r, 4),
        "profit_factor": round(pf, 3),
        "sharpe_r": round(sharpe, 3),
        "mean_mae_r": round(sum(t.mae_r for t in results) / n, 4),
        "mean_mfe_r": round(sum(t.mfe_r for t in results) / n, 4),
        "hit_rate_1272": round(hit_1272, 4),
        "hit_rate_1618": round(hit_1618, 4),
        "timeout_rate": round(tout, 4),
        "cagr": round(cagr, 5),
        "max_drawdown": round(max_dd, 5),
        "avg_bars_held": round(sum(t.bars_held for t in results) / n, 1),
        "exit_reasons": exit_reasons,
        "trigger_stats": trigger_stats,
        "start_equity": eq_vals[0],
        "end_equity": round(eq_vals[-1], 2),
    }


# ---------------------------------------------------------------------------
# Printed output
# ---------------------------------------------------------------------------


def print_report(exp_name: str, ticker: str, stats: dict, config) -> None:
    """Print single-experiment result block."""
    s = stats
    sep = "-" * 76
    print(f"\n{'=' * 76}")
    print(
        f"  FIB4  |  {exp_name}  ticker={ticker}"
        f"  Q>={config.quality_min_score:.0f}  trigger={config.entry_trigger}"
    )
    print(f"{'=' * 76}")
    print(sep)
    print(f"  Legs detected      : {s['n_legs']}")
    print(f"  Trades executed    : {s['n_trades']}  (zone_hit={s.get('zone_hit_rate', 0):.1%})")
    print(f"  Skipped setups     : {s['n_skipped']}  (skip_rate={s.get('skip_rate', 0):.1%})")
    if s["n_trades"] == 0:
        print("  No trades.")
        print(f"{'=' * 76}\n")
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

    # Trigger breakdown
    if s.get("trigger_stats"):
        print(sep)
        print("  Trigger breakdown  :")
        for trig, ts in s["trigger_stats"].items():
            print(
                f"    {trig:<32}  n={ts['n']:3d}  "
                f"win={ts['win_rate']:.1%}  avg_R={ts['avg_r']:+.3f}"
            )
    print(f"{'=' * 76}\n")


def print_comparison_table(rows: list[dict]) -> None:
    """
    Main fib4 vs fib3-baseline comparison table.

    Columns: Experiment | Ticker | Legs | Trades | Skip% | Win% | ExpR | PF | Sharpe | MaxDD
    """
    if not rows:
        return
    w = 126
    print(f"\n{'=' * w}")
    print("  FIB4 EXECUTION COMPARISON TABLE")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Experiment':<28}  {'Tkr':<4}  {'Legs':>5}  "
        f"{'Trd':>4}  {'Skip%':>5}  {'Win%':>5}  "
        f"{'ExpR':>7}  {'PF':>5}  {'Shr':>6}  "
        f"{'Hi1272':>6}  {'Hi1618':>6}  {'MaxDD':>7}"
    )
    print(hdr)
    print("-" * w)

    baseline_exp_r: dict[str, float] = {}

    for r in rows:
        s = r["stats"]
        ticker = r["ticker"]
        exp = r["exp"]
        is_baseline = exp.endswith("_baseline")

        if s["n_trades"] == 0:
            print(
                f"  {exp:<28}  {ticker:<4}  {s['n_legs']:>5}  "
                f"{'0':>4}  {s.get('skip_rate', 0):>5.1%}  {'--':>5}  "
                f"{'--':>7}  {'--':>5}  {'--':>6}  "
                f"{'--':>6}  {'--':>6}  {'--':>7}"
            )
            if is_baseline:
                baseline_exp_r[ticker] = 0.0
            continue

        exp_r = s["expectancy_r"]
        delta = ""
        if not is_baseline and ticker in baseline_exp_r:
            d = exp_r - baseline_exp_r[ticker]
            delta = f" ({d:+.3f})"

        if is_baseline:
            baseline_exp_r[ticker] = exp_r

        print(
            f"  {exp:<28}  {ticker:<4}  {s['n_legs']:>5}  "
            f"{s['n_trades']:>4}  {s.get('skip_rate', 0):>5.1%}  "
            f"{s['win_rate']:>5.1%}  {exp_r:>+7.3f}{delta:<10}  "
            f"{s['profit_factor']:>5.2f}  {s['sharpe_r']:>6.3f}  "
            f"{s['hit_rate_1272']:>6.1%}  {s['hit_rate_1618']:>6.1%}  "
            f"{s['max_drawdown']:>7.2%}"
        )

    print(f"{'=' * w}\n")


def print_verdict(rows: list[dict]) -> None:
    """
    Print a synthesis verdict based on the comparison data.
    Determines whether execution precision improved the edge.
    """
    if not rows:
        return

    # Find baseline and best per ticker
    baselines: dict[str, float] = {}
    bests: dict[str, tuple[str, float]] = {}

    for r in rows:
        s = r["stats"]
        if s["n_trades"] < 5:
            continue
        exp = r["exp"]
        ticker = r["ticker"]
        exp_r = s["expectancy_r"]

        if exp.endswith("_baseline"):
            baselines[ticker] = exp_r
        else:
            if ticker not in bests or exp_r > bests[ticker][1]:
                bests[ticker] = (exp, exp_r)

    print(f"\n{'=' * 76}")
    print("  FIB4 VERDICT: Did execution precision unlock the edge?")
    print(f"{'=' * 76}")

    for ticker in sorted(set(list(baselines.keys()) + list(bests.keys()))):
        base = baselines.get(ticker, float("nan"))
        best_exp, best_r = bests.get(ticker, ("none", float("nan")))

        if math.isnan(base) or math.isnan(best_r):
            print(f"  {ticker}: insufficient data")
            continue

        delta = best_r - base
        improved = delta > 0.05  # Meaningful improvement threshold

        marker = "YES" if improved else "NO "
        print(
            f"  {ticker}:  baseline={base:+.3f}R  "
            f"best={best_r:+.3f}R ({best_exp})  "
            f"delta={delta:+.3f}R  -> improved={marker}"
        )

    print(f"\n  STRATEGY ROLE ASSESSMENT")
    print(f"  -------------------------")

    any_positive = any(
        r["stats"].get("expectancy_r", 0) > 0.10 and r["stats"]["n_trades"] >= 5
        for r in rows
        if not r["exp"].endswith("_baseline")
    )
    any_significant = any(
        r["stats"].get("expectancy_r", 0) > 0.30 and r["stats"]["n_trades"] >= 5
        for r in rows
        if not r["exp"].endswith("_baseline")
    )

    if any_significant:
        print("  [STANDALONE] Execution-triggered entries show positive expectancy")
        print("               (ExpR > 0.30R). Viable as standalone with correct")
        print("               leg selection + execution discipline.")
    elif any_positive:
        print("  [CONFLUENCE] Positive but modest ExpR (0.10-0.30R). Best used as")
        print("               a confluence filter or target projection tool, not")
        print("               as a standalone trading strategy.")
    else:
        print("  [MAP-ONLY]   No execution variant consistently produced positive")
        print("               expectancy. Fib levels serve as a price map and")
        print("               context tool, not a tradeable edge.")

    print(f"{'=' * 76}\n")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 1e-9
    m = sum(vals) / len(vals)
    var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    return math.sqrt(max(var, 0))


def _equity_stats(eq_vals: list[float], bar_indices: list[int]) -> tuple[float, float]:
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
