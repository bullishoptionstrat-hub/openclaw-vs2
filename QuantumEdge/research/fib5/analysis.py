"""
fib5 analysis helpers — stats, formatted tables, verdicts.
"""

from __future__ import annotations

import math
from typing import Optional


# ---------------------------------------------------------------------------
# Core stats
# ---------------------------------------------------------------------------


def compute_stats(results: list, n_legs: int, n_skipped: int) -> dict:
    """Extended stats from StrictTradeResult list + skip tracking."""
    if not results:
        return {
            "n_legs": n_legs,
            "n_trades": 0,
            "n_skipped": n_skipped,
            "skip_rate": round(n_skipped / max(n_legs, 1), 4),
            "zone_hit_rate": 0.0,
            "win_rate": 0.0,
            "expectancy_r": 0.0,
            "profit_factor": 0.0,
            "sharpe_r": 0.0,
            "sortino_r": 0.0,
            "hit_rate_1272": 0.0,
            "hit_rate_1618": 0.0,
            "timeout_rate": 0.0,
            "cagr": 0.0,
            "max_drawdown": 0.0,
            "avg_bars_held": 0.0,
        }

    n = len(results)
    r_vals = [t.r_multiple for t in results]
    wins = [t for t in results if t.r_multiple > 0]

    win_rate = len(wins) / n
    mean_r = sum(r_vals) / n

    std_r = _std(r_vals)
    neg_r = [r for r in r_vals if r < 0]
    down_std = _std(neg_r) if neg_r else 1e-9
    sharpe = mean_r / std_r if std_r > 0 else 0.0
    sortino = mean_r / down_std if down_std > 0 else 0.0

    gw = sum(r for r in r_vals if r > 0)
    gl = abs(sum(r for r in r_vals if r < 0))
    pf = gw / gl if gl > 0 else float("inf")

    hit_1272 = sum(1 for t in results if t.reached_1272) / n
    hit_1618 = sum(1 for t in results if t.reached_1618) / n
    tout = sum(1 for t in results if t.exit_reason == "timeout") / n

    # Direction breakdown
    n_bull = sum(1 for t in results if getattr(t.leg, "direction", "") == "bullish")
    n_bear = n - n_bull
    dominant = "bullish" if n_bull >= n_bear else "bearish"

    eq = [results[0].equity_before] + [t.equity_after for t in results]
    bars = [t.entry_bar for t in results]
    cagr, max_dd = _equity_stats(eq, bars)

    return {
        "n_legs": n_legs,
        "n_trades": n,
        "n_skipped": n_skipped,
        "skip_rate": round(n_skipped / max(n_legs, 1), 4),
        "zone_hit_rate": round(n / max(n_legs, 1), 4),
        "win_rate": round(win_rate, 4),
        "expectancy_r": round(mean_r, 4),
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
        "n_bullish": n_bull,
        "n_bearish": n_bear,
        "dominant_direction": dominant,
    }


def compute_stats_from_r(adj_r_vals: list[float]) -> dict:
    """Minimal stats from a list of R multiples (for friction-adjusted)."""
    if not adj_r_vals:
        return {"n": 0, "win_rate": 0.0, "exp_r": 0.0, "pf": 0.0}
    n = len(adj_r_vals)
    wins = sum(1 for r in adj_r_vals if r > 0)
    gw = sum(r for r in adj_r_vals if r > 0)
    gl = abs(sum(r for r in adj_r_vals if r < 0))
    return {
        "n": n,
        "win_rate": round(wins / n, 4),
        "exp_r": round(sum(adj_r_vals) / n, 4),
        "pf": round(gw / gl, 3) if gl > 0 else float("inf"),
    }


# ---------------------------------------------------------------------------
# Replication table
# ---------------------------------------------------------------------------


def print_replication_table(rows: list[dict]) -> None:
    """
    Columns: Strategy | Ticker | Legs | Trades | Win% | ExpR | PF | Sortino | MaxDD
    """
    if not rows:
        return
    w = 120
    print(f"\n{'=' * w}")
    print("  FIB5 TRACK 1 -- REPLICATION TABLE")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Strategy':<14}  {'Ticker':<5}  {'Legs':>5}  {'Trd':>4}  "
        f"{'Skip%':>5}  {'Win%':>5}  {'ExpR':>7}  {'PF':>5}  "
        f"{'Shr':>5}  {'Sor':>5}  {'Hi1272':>6}  {'Hi1618':>6}  "
        f"{'MaxDD':>7}  {'AvgHld':>6}"
    )
    print(hdr)
    print("-" * w)

    prev_strategy = None
    for r in rows:
        s = r["stats"]
        if s["n_trades"] == 0:
            print(
                f"  {r['strategy']:<14}  {r['ticker']:<5}  {s['n_legs']:>5}  "
                f"{'0':>4}  {s['skip_rate']:>5.1%}  {'--':>5}  "
                f"{'--':>7}  {'--':>5}  {'--':>5}  {'--':>5}  "
                f"{'--':>6}  {'--':>6}  {'--':>7}  {'--':>6}"
            )
            prev_strategy = r["strategy"]
            continue

        # Visual separator between strategies
        if prev_strategy is not None and prev_strategy != r["strategy"]:
            print()
        prev_strategy = r["strategy"]

        print(
            f"  {r['strategy']:<14}  {r['ticker']:<5}  {s['n_legs']:>5}  "
            f"{s['n_trades']:>4}  {s['skip_rate']:>5.1%}  "
            f"{s['win_rate']:>5.1%}  {s['expectancy_r']:>+7.3f}  "
            f"{s['profit_factor']:>5.2f}  {s['sharpe_r']:>5.3f}  "
            f"{s['sortino_r']:>5.3f}  {s['hit_rate_1272']:>6.1%}  "
            f"{s['hit_rate_1618']:>6.1%}  {s['max_drawdown']:>7.2%}  "
            f"{s['avg_bars_held']:>6.1f}"
        )
    print(f"{'=' * w}\n")


# ---------------------------------------------------------------------------
# OOS table
# ---------------------------------------------------------------------------


def print_oos_table(splits: list[dict]) -> None:
    """IS vs OOS1 vs OOS2 comparison."""
    if not splits:
        return
    w = 106
    print(f"\n{'=' * w}")
    print("  FIB5 TRACK 2 -- OUT-OF-SAMPLE RESULTS")
    print(f"  IS: 2007-2016  |  OOS1: 2017-2022  |  OOS2: 2023+")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Strategy':<14}  {'Ticker':<5}  {'Period':<10}  "
        f"{'Legs':>5}  {'Trd':>4}  {'Win%':>5}  {'ExpR':>7}  "
        f"{'PF':>5}  {'MaxDD':>7}  {'AdjExpR':>8}"
    )
    print(hdr)
    print("-" * w)

    for split in splits:
        strat = split["strategy"]
        ticker = split["ticker"]
        periods = [
            ("IS", split.get("is")),
            ("OOS1", split.get("oos1")),
            ("OOS2", split.get("oos2")),
        ]
        for period_name, s in periods:
            if s is None:
                print(f"  {strat:<14}  {ticker:<5}  {period_name:<10}  [no data]")
                continue
            if s["n_trades"] == 0:
                print(
                    f"  {strat:<14}  {ticker:<5}  {period_name:<10}  "
                    f"{s['n_legs']:>5}  {'0':>4}  {'--':>5}  {'--':>7}  "
                    f"{'--':>5}  {'--':>7}  {'--':>8}"
                )
                continue

            adj_r = s.get("adj_expectancy_r", s["expectancy_r"])
            print(
                f"  {strat:<14}  {ticker:<5}  {period_name:<10}  "
                f"{s['n_legs']:>5}  {s['n_trades']:>4}  "
                f"{s['win_rate']:>5.1%}  {s['expectancy_r']:>+7.3f}  "
                f"{s['profit_factor']:>5.2f}  {s['max_drawdown']:>7.2%}  "
                f"{adj_r:>+8.3f}"
            )
        print()
    print(f"{'=' * w}\n")


# ---------------------------------------------------------------------------
# Robustness table
# ---------------------------------------------------------------------------


def print_robustness_table(
    xlk_summary: dict,
    qqq_summary: dict,
    xlk_grid: list[dict],
    qqq_grid: list[dict],
) -> None:
    """Print robustness grid summary (plateau vs peak)."""
    w = 76
    print(f"\n{'=' * w}")
    print("  FIB5 TRACK 3 -- PARAMETER ROBUSTNESS")
    print(f"{'=' * w}")

    for label, summary, grid in [
        ("XLK-style (sweep_deep + touch_rejection)", xlk_summary, xlk_grid),
        ("QQQ-style (midzone_only, Q>=60)", qqq_summary, qqq_grid),
    ]:
        print(f"\n  {label}")
        print(f"  {'-' * 50}")
        if not summary:
            print("  No data")
            continue
        n_cfg = summary.get("n_configs", 0)
        n_w = summary.get("n_with_trades", 0)
        n_pos = summary.get("n_positive", 0)
        n_10 = summary.get("n_gt_0.10R", 0)
        n_20 = summary.get("n_gt_0.20R", 0)
        pos_rate = summary.get("positive_rate", 0)
        print(f"  Configurations: {n_cfg}  (with>=5 trades: {n_w})")
        print(f"  Positive ExpR:  {n_pos}/{n_w}  ({pos_rate:.0%})")
        print(f"  ExpR > 0.10R:   {n_10}/{n_w}")
        print(f"  ExpR > 0.20R:   {n_20}/{n_w}")
        print(
            f"  Distribution:   "
            f"min={summary.get('min_exp_r', 0):+.3f}  "
            f"Q25={summary.get('q25_exp_r', 0):+.3f}  "
            f"med={summary.get('median_exp_r', 0):+.3f}  "
            f"Q75={summary.get('q75_exp_r', 0):+.3f}  "
            f"max={summary.get('max_exp_r', 0):+.3f}"
        )
        # ASCII histogram
        _print_ascii_hist([r["exp_r"] for r in grid if r["n_trades"] >= 5])

    print(f"{'=' * w}\n")


def _print_ascii_hist(values: list[float], bins: int = 10) -> None:
    if not values:
        return
    lo, hi = min(values), max(values)
    if lo == hi:
        return
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(int((v - lo) / width), bins - 1)
        counts[idx] += 1
    max_c = max(counts)
    bar_scale = 20
    print("  ExpR histogram (each bin width {:.3f}):".format(width))
    for i, c in enumerate(counts):
        lb = lo + i * width
        bar = "#" * int(c / max_c * bar_scale) if max_c > 0 else ""
        print(f"    {lb:+.3f} | {bar:<20} {c}")


# ---------------------------------------------------------------------------
# Friction table
# ---------------------------------------------------------------------------


def print_friction_table(friction_rows: list[dict]) -> None:
    """Show raw vs friction-adjusted ExpR per strategy x ticker."""
    if not friction_rows:
        return
    w = 90
    print(f"\n{'=' * w}")
    print("  FIB5 TRACK 4 -- FRICTION ADJUSTMENT  (5bps slippage round-trip)")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Strategy':<14}  {'Ticker':<5}  {'Trd':>4}  "
        f"{'Raw ExpR':>8}  {'5bps ExpR':>10}  {'10bps ExpR':>11}  {'Survives?':>10}"
    )
    print(hdr)
    print("-" * w)
    for r in friction_rows:
        raw = r.get("raw_exp_r", 0.0)
        adj5 = r.get("adj_exp_r_5bps", 0.0)
        adj10 = r.get("adj_exp_r_10bps", 0.0)
        n = r.get("n_trades", 0)
        if n == 0:
            print(
                f"  {r['strategy']:<14}  {r['ticker']:<5}  {'0':>4}  {'--':>8}  {'--':>10}  {'--':>11}  {'--':>10}"
            )
            continue
        survives = "YES" if adj5 > 0.0 else "NO "
        print(
            f"  {r['strategy']:<14}  {r['ticker']:<5}  {n:>4}  "
            f"{raw:>+8.3f}  {adj5:>+10.3f}  {adj10:>+11.3f}  {survives:>10}"
        )
    print(f"{'=' * w}\n")


# ---------------------------------------------------------------------------
# Regime table
# ---------------------------------------------------------------------------


def print_regime_table(
    decomp: dict,
    strategy: str,
    ticker: str,
) -> None:
    """Print regime decomposition for one strategy x ticker."""
    if not decomp:
        return
    print(f"\n  Regime breakdown: {strategy} / {ticker}")
    print(f"  {'-' * 60}")
    print(f"  {'Regime':<22}  {'n':>4}  {'Win%':>5}  {'ExpR':>7}  {'AvgMAE':>7}  {'AvgMFE':>7}")
    for key, d in sorted(decomp.items(), key=lambda x: -x[1]["n"]):
        print(
            f"  {key:<22}  {d['n']:>4}  {d['win_rate']:>5.1%}  "
            f"{d['exp_r']:>+7.3f}  {d['avg_mae_r']:>7.3f}  {d['avg_mfe_r']:>7.3f}"
        )


# ---------------------------------------------------------------------------
# Final verdict
# ---------------------------------------------------------------------------


def print_final_verdict(
    replication_rows: list[dict],
    oos_splits: list[dict],
    rob_xlk: dict,
    rob_qqq: dict,
    friction_rows: list[dict],
) -> None:
    """
    Synthesize all tracks into a deployment verdict.
    Verdict categories:
      STANDALONE  — replicates + OOS positive + robust + survives friction
      CONFLUENCE  — positive but not robust enough for standalone
      OVERLAY     — good as signal filter or target tool but not edge source
      MAP-ONLY    — no consistent edge; use for structure mapping only
    """
    print(f"\n{'#' * 76}")
    print("  FIB5 FINAL VERDICT")
    print(f"{'#' * 76}")

    # Per-strategy summary
    strategies = list({r["strategy"] for r in replication_rows})
    for strat in sorted(strategies):
        rows = [r for r in replication_rows if r["strategy"] == strat]
        n_positive = sum(
            1 for r in rows if r["stats"]["n_trades"] >= 5 and r["stats"]["expectancy_r"] > 0
        )
        n_tested = sum(1 for r in rows if r["stats"]["n_trades"] >= 5)
        positive_rate = n_positive / n_tested if n_tested > 0 else 0.0

        # OOS check
        oos_rows = [s for s in oos_splits if s["strategy"] == strat]
        oos_positive = 0
        oos_tested = 0
        for s in oos_rows:
            oos1 = s.get("oos1")
            if oos1 and oos1["n_trades"] >= 3:
                oos_tested += 1
                if oos1["expectancy_r"] > 0:
                    oos_positive += 1

        oos_rate = oos_positive / oos_tested if oos_tested > 0 else float("nan")

        # Robustness check
        if strat == "xlk_style":
            rob = rob_xlk
        elif strat == "qqq_style":
            rob = rob_qqq
        else:
            rob = {}
        rob_positive = rob.get("positive_rate", float("nan"))

        # Friction check
        fric_rows = [r for r in friction_rows if r["strategy"] == strat and r["n_trades"] >= 5]
        fric_survive = sum(1 for r in fric_rows if r.get("adj_exp_r_5bps", 0) > 0)
        fric_tested = len(fric_rows)
        fric_rate = fric_survive / fric_tested if fric_tested > 0 else float("nan")

        print(f"\n  Strategy: {strat}")
        print(f"  {'Replication':<22}: {n_positive}/{n_tested} positive ({positive_rate:.0%})")
        if not math.isnan(oos_rate):
            print(
                f"  {'OOS (2017-2022)':<22}: {oos_positive}/{oos_tested} positive ({oos_rate:.0%})"
            )
        if not math.isnan(rob_positive):
            print(f"  {'Robustness':<22}: {rob_positive:.0%} of grid configs positive")
        if not math.isnan(fric_rate):
            print(f"  {'Friction (5bps)':<22}: {fric_survive}/{fric_tested} survive slippage")

        # Verdict logic
        criteria_met = []
        if positive_rate >= 0.50:
            criteria_met.append("replicates")
        if not math.isnan(oos_rate) and oos_rate >= 0.50:
            criteria_met.append("OOS_positive")
        if not math.isnan(rob_positive) and rob_positive >= 0.60:
            criteria_met.append("robust")
        if not math.isnan(fric_rate) and fric_rate >= 0.67:
            criteria_met.append("friction_ok")

        n_met = len(criteria_met)
        if n_met >= 4:
            role = "STANDALONE  -- meets all deployment criteria"
        elif n_met >= 3:
            role = "CONFLUENCE  -- use as high-conviction filter; not standalone"
        elif n_met >= 2:
            role = "OVERLAY     -- useful as regime/target tool; edge not consistent"
        else:
            role = "MAP-ONLY    -- structural tool only; no consistent trading edge"

        print(f"  {'Criteria met':<22}: {criteria_met}")
        print(f"  ROLE: {role}")

    print(f"\n{'#' * 76}")
    print("  NEXT HIGHEST-VALUE STEP")
    print(f"{'#' * 76}")
    print("  1. If xlk_style / qqq_style replicate: expand to all sector ETFs")
    print("     and confirm edge is sector-ETF-specific, not broad-market")
    print("  2. Add 1H execution for any instrument where hourly data is available")
    print("  3. If OOS degrades significantly: investigate regime dependency")
    print("     (the edge may be specific to the pre-2017 tech expansion regime)")
    print("  4. If robust: build position-sizing framework for sector rotation")
    print("  5. If map-only: use fib levels as target/exit layer only")
    print(f"{'#' * 76}\n")


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
        peak = max(peak, v)
        dd = (v - peak) / peak
        max_dd = min(max_dd, dd)
    return cagr, max_dd
