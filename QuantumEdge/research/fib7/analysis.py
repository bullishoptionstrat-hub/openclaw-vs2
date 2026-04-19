"""
fib7 analysis: stats, tables, and deployment classification.

Extends fib6 analysis with:
  1. LIVE-READY CANDIDATE tier (above DEPLOYMENT CANDIDATE)
  2. Track B QQQ regime paradox resolution table
  3. Track C SPY combined-gate table
  4. Track D rotation comparison table
  5. Track E live spec summary
"""

from __future__ import annotations

import math
from typing import Optional


# ---------------------------------------------------------------------------
# Core stats (unchanged from fib6, re-exported for convenience)
# ---------------------------------------------------------------------------


def compute_stats(
    results: list,
    n_legs: int,
    n_skipped: int,
    n_regime_filtered: int = 0,
) -> dict:
    if not results:
        return {
            "n_legs": n_legs,
            "n_trades": 0,
            "n_skipped": n_skipped,
            "n_regime_filtered": n_regime_filtered,
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

    n_bull = sum(1 for t in results if getattr(t.leg, "direction", "") == "bullish")
    n_bear = n - n_bull

    eq = [results[0].equity_before] + [t.equity_after for t in results]
    bars = [t.entry_bar for t in results]
    cagr, max_dd = _equity_stats(eq, bars)

    return {
        "n_legs": n_legs,
        "n_trades": n,
        "n_skipped": n_skipped,
        "n_regime_filtered": n_regime_filtered,
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
        "dominant_direction": "bullish" if n_bull >= n_bear else "bearish",
    }


# ---------------------------------------------------------------------------
# Table: Track A -- XLK hardening neighborhood
# ---------------------------------------------------------------------------


def print_tracka_hardening_table(rows: list[dict]) -> None:
    """
    Rows: {config, ticker, stats, gate, trigger, stop, target}
    """
    if not rows:
        return
    w = 120
    print(f"\n{'=' * w}")
    print("  FIB7 TRACK A -- XLK DEPLOYMENT HARDENING")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Config':<28}  {'Tkr':<4}  {'Gate':<10}  {'Trig':<16}  "
        f"{'Stop':<8}  {'Tgt':>5}  {'Trd':>4}  {'Win%':>5}  "
        f"{'ExpR':>7}  {'PF':>5}  {'Sharpe':>6}  {'MaxDD':>7}  {'5bps':>7}"
    )
    print(hdr)
    print("-" * w)
    for r in rows:
        s = r["stats"]
        adj5 = r.get("adj_exp_r_5bps", None)
        adj5_str = f"{adj5:>+7.3f}" if adj5 is not None else f"{'--':>7}"
        if s["n_trades"] == 0:
            print(
                f"  {r['config']:<28}  {r.get('ticker', '--'):<4}  "
                f"{r.get('gate', '--'):<10}  {r.get('trigger', '--'):<16}  "
                f"{r.get('stop', '--'):<8}  {r.get('target', 0):>5.3f}  "
                f"{'0':>4}  {'--':>5}  {'--':>7}  {'--':>5}  {'--':>6}  {'--':>7}  {adj5_str}"
            )
            continue
        print(
            f"  {r['config']:<28}  {r.get('ticker', '--'):<4}  "
            f"{r.get('gate', '--'):<10}  {r.get('trigger', '--'):<16}  "
            f"{r.get('stop', '--'):<8}  {r.get('target', 0):>5.3f}  "
            f"{s['n_trades']:>4}  {s['win_rate']:>5.1%}  {s['expectancy_r']:>+7.3f}  "
            f"{s['profit_factor']:>5.2f}  {s['sharpe_r']:>6.3f}  "
            f"{s['max_drawdown']:>7.2%}  {adj5_str}"
        )
    print(f"{'=' * w}\n")


# ---------------------------------------------------------------------------
# Table: Track B -- QQQ regime paradox resolution
# ---------------------------------------------------------------------------


def print_trackb_paradox_table(rows: list[dict]) -> None:
    """
    Rows: {config, ticker, regime_bar, gate, stats}
    Shows all bar-type x gate combinations for QQQ.
    """
    if not rows:
        return
    w = 112
    print(f"\n{'=' * w}")
    print("  FIB7 TRACK B -- QQQ REGIME PARADOX RESOLUTION")
    print(f"  Comparing vol gate at: discovery_bar vs completion_bar vs anchor_bar")
    print(f"  fib5 finding: vol_active wins at completion_bar")
    print(f"  fib6 finding: vol_quiet wins at discovery_bar")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Config':<26}  {'Tkr':<4}  {'RegBar':<11}  {'Gate':<11}  "
        f"{'Trd':>4}  {'Win%':>5}  {'ExpR':>7}  {'PF':>5}  {'Sharpe':>6}  "
        f"{'MaxDD':>7}  {'RegFlt':>6}"
    )
    print(hdr)
    print("-" * w)

    prev_regime_bar = None
    for r in rows:
        s = r["stats"]
        rb = r.get("regime_bar", "discovery")
        if prev_regime_bar is not None and prev_regime_bar != rb:
            print()
        prev_regime_bar = rb

        reg_flt = s.get("n_regime_filtered", 0)
        if s["n_trades"] == 0:
            print(
                f"  {r['config']:<26}  {r.get('ticker', '--'):<4}  "
                f"{rb:<11}  {r.get('gate', '--'):<11}  "
                f"{'0':>4}  {'--':>5}  {'--':>7}  {'--':>5}  {'--':>6}  {'--':>7}  {reg_flt:>6}"
            )
            continue
        print(
            f"  {r['config']:<26}  {r.get('ticker', '--'):<4}  "
            f"{rb:<11}  {r.get('gate', '--'):<11}  "
            f"{s['n_trades']:>4}  {s['win_rate']:>5.1%}  {s['expectancy_r']:>+7.3f}  "
            f"{s['profit_factor']:>5.2f}  {s['sharpe_r']:>6.3f}  "
            f"{s['max_drawdown']:>7.2%}  {reg_flt:>6}"
        )
    print(f"{'=' * w}\n")


def print_trackb_paradox_summary(rows: list[dict]) -> None:
    """Summary: for each regime_bar type, which gate wins?"""
    w = 76
    print(f"\n{'=' * w}")
    print("  FIB7 TRACK B -- PARADOX RESOLUTION VERDICT")
    print(f"{'=' * w}")

    # Group by regime_bar, find best gate for each
    from collections import defaultdict

    by_rb: dict[str, list] = defaultdict(list)
    for r in rows:
        rb = r.get("regime_bar", "discovery")
        by_rb[rb].append(r)

    neutral_exp: dict[str, float] = {}
    for rb, rb_rows in by_rb.items():
        for r in rb_rows:
            if r.get("gate") == "neutral":
                neutral_exp[rb] = r["stats"]["expectancy_r"]

    print(
        f"\n  {'Bar type':<12}  {'Gate':<12}  {'Neutral ExpR':>12}  {'Gate ExpR':>9}  {'Delta':>7}  {'Verdict'}"
    )
    print(f"  {'-' * 65}")
    for rb in ["discovery", "completion", "anchor"]:
        rb_rows = by_rb.get(rb, [])
        n_exp = neutral_exp.get(rb, 0.0)
        for r in rb_rows:
            if r.get("gate") == "neutral":
                continue
            gate = r.get("gate", "?")
            g_exp = r["stats"]["expectancy_r"]
            delta = g_exp - n_exp
            n_trades = r["stats"]["n_trades"]
            if n_trades < 5:
                verdict = "LOW SAMPLE"
            elif delta > 0.10 and g_exp > 0:
                verdict = "IMPROVED +"
            elif delta < -0.10:
                verdict = "DEGRADED  -"
            else:
                verdict = "NEUTRAL   ="
            print(
                f"  {rb:<12}  {gate:<12}  {n_exp:>+12.3f}  {g_exp:>+9.3f}  "
                f"{delta:>+7.3f}  {verdict}"
            )
        print()

    print(f"{'=' * w}\n")


# ---------------------------------------------------------------------------
# Table: Track C -- SPY combined gate x trigger
# ---------------------------------------------------------------------------


def print_trackc_spy_combined_table(rows: list[dict]) -> None:
    """
    Rows: {config, gate, trigger, data_source, stats, vs_baseline_exp_r}
    """
    if not rows:
        return
    w = 104
    print(f"\n{'=' * w}")
    print("  FIB7 TRACK C -- SPY VOL GATE x 1H TRIGGER COMBINED")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Config':<28}  {'Gate':<11}  {'Trigger':<20}  "
        f"{'Trd':>4}  {'Win%':>5}  {'ExpR':>7}  "
        f"{'Sharpe':>6}  {'MaxDD':>7}  {'vs_Base':>7}"
    )
    print(hdr)
    print("-" * w)

    prev_gate = None
    for r in rows:
        s = r["stats"]
        gate = r.get("gate", "neutral")
        if prev_gate is not None and prev_gate != gate:
            print()
        prev_gate = gate

        vs_base = r.get("vs_baseline_exp_r")
        vs_str = f"{vs_base:>+7.3f}" if vs_base is not None else f"{'(base)':>7}"

        if s["n_trades"] == 0:
            print(
                f"  {r['config']:<28}  {gate:<11}  {r.get('trigger', '--'):<20}  "
                f"{'0':>4}  {'--':>5}  {'--':>7}  {'--':>6}  {'--':>7}  {vs_str}"
            )
            continue
        print(
            f"  {r['config']:<28}  {gate:<11}  {r.get('trigger', '--'):<20}  "
            f"{s['n_trades']:>4}  {s['win_rate']:>5.1%}  {s['expectancy_r']:>+7.3f}  "
            f"{s['sharpe_r']:>6.3f}  {s['max_drawdown']:>7.2%}  {vs_str}"
        )
    print(f"{'=' * w}\n")


# ---------------------------------------------------------------------------
# Table: Track D -- Rotation engine comparison
# ---------------------------------------------------------------------------


def print_trackd_rotation_table(
    rotation_results: dict[str, dict],
    single_best: tuple[str, dict],
    fib6_portfolio_exp_r: Optional[float] = None,
) -> None:
    """
    rotation_results: {method_name: rotation_stats_dict}
    single_best: (ticker, stats)
    fib6_portfolio_exp_r: diluted fib6 portfolio ExpR for comparison
    """
    w = 88
    print(f"\n{'=' * w}")
    print("  FIB7 TRACK D -- SELECTIVE ROTATION ENGINE")
    print(f"  Rotation vs static portfolio vs single best")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Config':<26}  {'Trd':>5}  {'Win%':>5}  "
        f"{'ExpR':>7}  {'Sharpe':>6}  {'Sortino':>7}  "
        f"{'PF':>5}  {'MaxDD':>7}  {'Rotations':>9}"
    )
    print(hdr)
    print("-" * w)

    # Single best (static)
    sb_ticker, sb_stats = single_best
    if sb_stats:
        label = f"single_best ({sb_ticker})"
        print(
            f"  {label:<26}  {sb_stats.get('n_trades', 0):>5}  {'--':>5}  "
            f"{sb_stats.get('exp_r', 0):>+7.3f}  {sb_stats.get('sharpe_r', 0):>6.3f}  "
            f"{'--':>7}  {'--':>5}  {'--':>7}  {'--':>9}"
        )

    # fib6 diluted portfolio baseline
    if fib6_portfolio_exp_r is not None:
        print(
            f"  {'fib6_equal_weight_5inst':<26}  {'--':>5}  {'--':>5}  "
            f"{fib6_portfolio_exp_r:>+7.3f}  {'--':>6}  {'--':>7}  {'--':>5}  {'--':>7}  {'--':>9}"
        )
    print()

    for method, rstat in rotation_results.items():
        if rstat["n_trades"] == 0:
            print(
                f"  {method:<26}  {'0':>5}  {'--':>5}  {'--':>7}  "
                f"{'--':>6}  {'--':>7}  {'--':>5}  {'--':>7}  {'--':>9}"
            )
            continue
        rot_changes = rstat.get("rotation_changes", 0)
        print(
            f"  {method:<26}  {rstat['n_trades']:>5}  "
            f"{rstat['win_rate']:>5.1%}  {rstat['exp_r']:>+7.3f}  "
            f"{rstat['sharpe_r']:>6.3f}  {rstat['sortino_r']:>7.3f}  "
            f"{rstat['profit_factor']:>5.2f}  {rstat['max_drawdown']:>7.2%}  "
            f"{rot_changes:>9}"
        )
        # Ticker breakdown
        ts = rstat.get("ticker_summary", {})
        if ts:
            parts = [
                f"{t}:n={d['n_trades_total']},ExpR={d['trailing_exp_r']:+.3f}"
                for t, d in sorted(ts.items())
                if d["n_trades_total"] > 0
            ]
            if parts:
                print(f"    -> {' | '.join(parts)}")

    print(f"{'=' * w}\n")


# ---------------------------------------------------------------------------
# OOS table (reused from fib6 pattern)
# ---------------------------------------------------------------------------


def print_oos_table(oos_splits: list[dict], title: str = "FIB7 OOS VALIDATION") -> None:
    if not oos_splits:
        return
    w = 112
    print(f"\n{'=' * w}")
    print(f"  {title}")
    print(f"  IS: 2007-2016  |  OOS1: 2017-2022  |  OOS2: 2023+")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Config':<26}  {'Ticker':<5}  {'Period':<8}  "
        f"{'Legs':>5}  {'Trd':>4}  {'Win%':>5}  {'ExpR':>7}  "
        f"{'PF':>5}  {'MaxDD':>7}  {'AdjExpR':>8}"
    )
    print(hdr)
    print("-" * w)

    for split in oos_splits:
        cfg = split["config"]
        ticker = split["ticker"]
        for period_name, s in [
            ("IS", split.get("is")),
            ("OOS1", split.get("oos1")),
            ("OOS2", split.get("oos2")),
        ]:
            if s is None:
                print(f"  {cfg:<26}  {ticker:<5}  {period_name:<8}  [no data]")
                continue
            if s["n_trades"] == 0:
                print(
                    f"  {cfg:<26}  {ticker:<5}  {period_name:<8}  "
                    f"{s['n_legs']:>5}  {'0':>4}  {'--':>5}  {'--':>7}  "
                    f"{'--':>5}  {'--':>7}  {'--':>8}"
                )
                continue
            adj_r = s.get("adj_expectancy_r", s["expectancy_r"])
            print(
                f"  {cfg:<26}  {ticker:<5}  {period_name:<8}  "
                f"{s['n_legs']:>5}  {s['n_trades']:>4}  "
                f"{s['win_rate']:>5.1%}  {s['expectancy_r']:>+7.3f}  "
                f"{s['profit_factor']:>5.2f}  {s['max_drawdown']:>7.2%}  "
                f"{adj_r:>+8.3f}"
            )
        print()
    print(f"{'=' * w}\n")


def print_friction_table(friction_rows: list[dict], title: str = "FIB7 FRICTION ANALYSIS") -> None:
    if not friction_rows:
        return
    w = 92
    print(f"\n{'=' * w}")
    print(f"  {title}")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Config':<26}  {'Ticker':<5}  {'Trd':>4}  "
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
                f"  {r['config']:<26}  {r['ticker']:<5}  {'0':>4}  "
                f"{'--':>8}  {'--':>10}  {'--':>11}  {'--':>10}"
            )
            continue
        survives = "YES" if adj5 > 0.0 else "NO "
        print(
            f"  {r['config']:<26}  {r['ticker']:<5}  {n:>4}  "
            f"{raw:>+8.3f}  {adj5:>+10.3f}  {adj10:>+11.3f}  {survives:>10}"
        )
    print(f"{'=' * w}\n")


def print_robustness_summary(label: str, summary: dict, grid: list[dict]) -> None:
    print(f"\n  {label}")
    print(f"  {'-' * 60}")
    if not summary:
        print("  No data")
        return
    n_cfg = summary.get("n_configs", 0)
    n_w = summary.get("n_with_trades", 0)
    n_pos = summary.get("n_positive", 0)
    n_10 = summary.get("n_gt_0.10R", 0)
    n_20 = summary.get("n_gt_0.20R", 0)
    pos_rate = summary.get("positive_rate", 0)
    print(f"  Configurations: {n_cfg}  (with >=5 trades: {n_w})")
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
    exp_rs = [r["exp_r"] for r in grid if r["n_trades"] >= 5]
    _print_ascii_hist(exp_rs)


# ---------------------------------------------------------------------------
# Classification (extends fib6 with LIVE-READY tier)
# ---------------------------------------------------------------------------

REJECT = "REJECT"
MAP_ONLY = "MAP ONLY"
CONFLUENCE_ONLY = "CONFLUENCE ONLY"
STANDALONE_CAND = "STANDALONE CANDIDATE"
DEPLOYMENT_CAND = "DEPLOYMENT CANDIDATE"
LIVE_READY = "LIVE-READY CANDIDATE"


def classify_config(
    config_name: str,
    rep_rows: list[dict],
    oos_splits: list[dict],
    rob_summary: Optional[dict],
    friction_rows: list[dict],
    oos2_splits: Optional[list[dict]] = None,
    live_spec_complete: bool = False,
    min_trades: int = 5,
) -> dict:
    """
    Evaluate config against criteria and assign fib7 classification.

    Standard criteria (same as fib6):
      replicates   : positive ExpR on >= 50% of tested instruments
      oos_positive : OOS1 positive on >= 50% of tested instruments
      robust       : >= 60% of grid configs positive
      friction_ok  : >= 67% of instruments survive 5bps

    LIVE-READY additional criteria (above DEPLOYMENT CANDIDATE):
      oos2_positive : OOS2 positive on >= 50% of tested instruments
      live_spec     : live signal spec is complete and feasible
    """
    criteria_met = []
    evidence = []

    # 1. Replication
    tested = [r for r in rep_rows if r["stats"]["n_trades"] >= min_trades]
    positive = [r for r in tested if r["stats"]["expectancy_r"] > 0]
    rep_rate = len(positive) / len(tested) if tested else 0.0
    if rep_rate >= 0.50:
        criteria_met.append("replicates")
    evidence.append(f"rep={len(positive)}/{len(tested)} ({rep_rate:.0%})")

    # 2. OOS1
    oos_tested = 0
    oos_positive = 0
    for split in oos_splits:
        oos1 = split.get("oos1")
        if oos1 and oos1["n_trades"] >= 3:
            oos_tested += 1
            if oos1["expectancy_r"] > 0:
                oos_positive += 1
    oos_rate = oos_positive / oos_tested if oos_tested > 0 else float("nan")
    if not math.isnan(oos_rate) and oos_rate >= 0.50:
        criteria_met.append("oos_positive")
    if not math.isnan(oos_rate):
        evidence.append(f"oos1={oos_positive}/{oos_tested} ({oos_rate:.0%})")

    # 3. Robustness
    rob_pos_rate = rob_summary.get("positive_rate", float("nan")) if rob_summary else float("nan")
    if not math.isnan(rob_pos_rate) and rob_pos_rate >= 0.60:
        criteria_met.append("robust")
    if not math.isnan(rob_pos_rate):
        evidence.append(f"rob={rob_pos_rate:.0%}")

    # 4. Friction
    fric_tested = [r for r in friction_rows if r.get("n_trades", 0) >= min_trades]
    fric_survive = [r for r in fric_tested if r.get("adj_exp_r_5bps", 0) > 0]
    fric_rate = len(fric_survive) / len(fric_tested) if fric_tested else float("nan")
    if not math.isnan(fric_rate) and fric_rate >= 0.67:
        criteria_met.append("friction_ok")
    if not math.isnan(fric_rate):
        evidence.append(f"fric={len(fric_survive)}/{len(fric_tested)} ({fric_rate:.0%})")

    # Standard classification
    n_met = len(criteria_met)
    if n_met >= 4:
        base_role = DEPLOYMENT_CAND
    elif n_met >= 3:
        base_role = STANDALONE_CAND
    elif n_met >= 2:
        base_role = CONFLUENCE_ONLY
    elif n_met >= 1:
        base_role = MAP_ONLY
    else:
        base_role = REJECT

    # LIVE-READY upgrade (requires DEPLOYMENT CANDIDATE first)
    live_criteria = []
    if base_role == DEPLOYMENT_CAND:
        # OOS2 check
        if oos2_splits:
            oos2_tested = 0
            oos2_positive = 0
            for split in oos2_splits:
                oos2 = split.get("oos2")
                if oos2 and oos2["n_trades"] >= 3:
                    oos2_tested += 1
                    if oos2["expectancy_r"] > 0:
                        oos2_positive += 1
            oos2_rate = oos2_positive / oos2_tested if oos2_tested > 0 else float("nan")
            if not math.isnan(oos2_rate) and oos2_rate >= 0.50:
                live_criteria.append("oos2_positive")
            if not math.isnan(oos2_rate):
                evidence.append(f"oos2={oos2_positive}/{oos2_tested} ({oos2_rate:.0%})")

        if live_spec_complete:
            live_criteria.append("live_spec")

    criteria_met.extend(live_criteria)

    if base_role == DEPLOYMENT_CAND and len(live_criteria) >= 2:
        role = LIVE_READY
    else:
        role = base_role

    return {
        "config": config_name,
        "criteria_met": criteria_met,
        "n_criteria": len(criteria_met),
        "classification": role,
        "evidence": evidence,
    }


def print_final_classification(classifications: list[dict]) -> None:
    w = 96
    print(f"\n{'#' * w}")
    print("  FIB7 -- SIGNAL ENGINE DEPLOYMENT CLASSIFICATION")
    print(f"{'#' * w}")
    print(f"\n  {'Config':<28}  {'Criteria':<50}  {'Classification'}")
    print(f"  {'-' * 90}")

    tier_order = {
        LIVE_READY: 0,
        DEPLOYMENT_CAND: 1,
        STANDALONE_CAND: 2,
        CONFLUENCE_ONLY: 3,
        MAP_ONLY: 4,
        REJECT: 5,
    }
    ranked = sorted(classifications, key=lambda x: tier_order.get(x["classification"], 6))

    prev_tier = None
    for c in ranked:
        tier = c["classification"]
        if prev_tier is not None and tier != prev_tier:
            print()
        prev_tier = tier

        criteria_str = " | ".join(c["criteria_met"]) if c["criteria_met"] else "(none)"
        print(f"  {c['config']:<28}  {criteria_str:<50}  {tier}")
        if c.get("evidence"):
            ev_str = "  ".join(c["evidence"])
            print(f"  {'':28}  Evidence: {ev_str}")

    print(f"\n{'#' * w}")
    print("  FIB7 DEPLOYMENT SUMMARY")
    print(f"{'#' * w}")
    live_ready = [c for c in ranked if c["classification"] == LIVE_READY]
    deploy = [c for c in ranked if c["classification"] == DEPLOYMENT_CAND]
    standalone = [c for c in ranked if c["classification"] == STANDALONE_CAND]

    if live_ready:
        print("  LIVE-READY CANDIDATES:")
        for c in live_ready:
            print(f"    {c['config']}: {c['classification']}  [{' | '.join(c['criteria_met'])}]")
    if deploy:
        print("  DEPLOYMENT CANDIDATES:")
        for c in deploy:
            print(f"    {c['config']}: {c['classification']}  [{' | '.join(c['criteria_met'])}]")
    if standalone:
        print("  STANDALONE CANDIDATES:")
        for c in standalone:
            print(f"    {c['config']}: {c['classification']}  [{' | '.join(c['criteria_met'])}]")
    if not live_ready and not deploy and not standalone:
        print("  No configs reached STANDALONE CANDIDATE or above.")
        if ranked:
            print(f"  Best: {ranked[0]['config']} -> {ranked[0]['classification']}")

    print(f"\n{'#' * w}")
    print("  NEXT HIGHEST-VALUE STEP")
    print(f"{'#' * w}")
    if live_ready:
        print("  1. Begin paper trading the LIVE-READY config with small notional")
        print("  2. Compare live signals against backtested armed/confirmed conditions")
        print("  3. Track fill quality: actual slippage vs modeled 5bps assumption")
        print(
            "  4. Set performance review trigger: if 20-trade rolling ExpR < 0 for 3 months, pause"
        )
        print("  5. Target: $25k-$50k live account after 6 months paper confirmation")
    elif deploy:
        print("  1. Complete OOS2 validation (2023+) for DEPLOYMENT candidates")
        print("  2. Generate live signal spec card (Track E) for each candidate")
        print("  3. If OOS2 positive: upgrade to LIVE-READY and begin paper trading")
    elif standalone:
        print("  1. Expand robustness grid: 3D neighborhood (stop x target x disp_atr)")
        print("  2. Add OOS2 validation for 2023+ period")
        print("  3. Test on 2 additional out-of-sample instruments")
    else:
        print("  1. Return to regime measurement: test ATR gate as primary filter")
        print("  2. Test longer vol lookback (40-bar) for smoother regime signal")
        print("  3. Consider combined filters: vol_quiet AND spy_bull for XLK configs")
    print(f"{'#' * w}\n")


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
    print("  ExpR histogram (bin width {:.3f}):".format(width))
    for i, c in enumerate(counts):
        lb = lo + i * width
        bar = "#" * int(c / max_c * 20) if max_c > 0 else ""
        print(f"    {lb:+.3f} | {bar:<20} {c}")
