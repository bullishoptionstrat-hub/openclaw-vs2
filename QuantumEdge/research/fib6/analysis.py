"""
fib6 analysis: stats, formatted output tables, and deployment classification.

Tables produced:
  1. Phase 1: Vol gate attribution table (per strategy x ticker x gate)
  2. Phase 2: 1H execution attribution table
  3. Phase 3: Portfolio comparison table
  4. Phase 4: OOS + friction table
  5. Regime attribution table (vol_quiet vs vol_active breakdown)
  6. Final deployment classification

All output uses ASCII-only characters for cross-platform compatibility.
"""

from __future__ import annotations

import math
from typing import Optional


# ---------------------------------------------------------------------------
# Core stats (extends fib5's compute_stats, adds n_regime_filtered)
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
# Table 1: Phase 1 -- Vol Gate Attribution
# ---------------------------------------------------------------------------


def print_phase1_vol_gate_table(rows: list[dict]) -> None:
    """
    Rows format: {config, ticker, gate, stats}
    Shows all 3 gate modes (neutral/vol_quiet/vol_active) per strategy x ticker.
    """
    if not rows:
        return
    w = 128
    print(f"\n{'=' * w}")
    print("  FIB6 TRACK A -- VOL REGIME GATE ATTRIBUTION")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Config':<16}  {'Ticker':<5}  {'Gate':<11}  "
        f"{'Legs':>5}  {'Trd':>4}  {'RegFlt':>6}  {'Win%':>5}  "
        f"{'ExpR':>7}  {'PF':>5}  {'Sharpe':>6}  {'MaxDD':>7}  "
        f"{'Hi1272':>6}  {'Tmout':>5}  {'AvgHld':>6}"
    )
    print(hdr)
    print("-" * w)

    prev_key = None
    for r in rows:
        s = r["stats"]
        key = (r.get("base_strategy", r["config"]), r["ticker"])
        if prev_key is not None and prev_key != key:
            print()
        prev_key = key

        gate = r.get("gate", "neutral")
        reg_flt = s.get("n_regime_filtered", 0)

        if s["n_trades"] == 0:
            print(
                f"  {r['config']:<16}  {r['ticker']:<5}  {gate:<11}  "
                f"{s['n_legs']:>5}  {'0':>4}  {reg_flt:>6}  {'--':>5}  "
                f"{'--':>7}  {'--':>5}  {'--':>6}  {'--':>7}  {'--':>6}  {'--':>5}  {'--':>6}"
            )
            continue

        print(
            f"  {r['config']:<16}  {r['ticker']:<5}  {gate:<11}  "
            f"{s['n_legs']:>5}  {s['n_trades']:>4}  {reg_flt:>6}  "
            f"{s['win_rate']:>5.1%}  {s['expectancy_r']:>+7.3f}  "
            f"{s['profit_factor']:>5.2f}  {s['sharpe_r']:>6.3f}  "
            f"{s['max_drawdown']:>7.2%}  "
            f"{s['hit_rate_1272']:>6.1%}  {s['timeout_rate']:>5.1%}  "
            f"{s['avg_bars_held']:>6.1f}"
        )
    print(f"{'=' * w}\n")


def print_vol_gate_summary(rows: list[dict]) -> None:
    """
    Attribution summary: for each strategy, show gate improvement vs neutral.
    """
    w = 96
    print(f"\n{'=' * w}")
    print("  FIB6 -- VOL GATE IMPROVEMENT SUMMARY")
    print(f"  Positive = gate improved vs neutral; Negative = gate degraded")
    print(f"{'=' * w}")
    print(
        f"  {'Strategy':<16}  {'Ticker':<5}  {'Gate':<11}  "
        f"{'ExpR_neutral':>12}  {'ExpR_gate':>9}  {'Delta':>7}  {'Trd':>4}  {'Result':<12}"
    )
    print("-" * w)

    # Group by (base_strategy, ticker)
    groups: dict[tuple, dict] = {}
    for r in rows:
        key = (r.get("base_strategy", r["config"]), r["ticker"])
        gate = r.get("gate", "neutral")
        if key not in groups:
            groups[key] = {}
        groups[key][gate] = r

    for (strat, ticker), gates in sorted(groups.items()):
        neutral = gates.get("neutral")
        neutral_exp = neutral["stats"]["expectancy_r"] if neutral else 0.0
        neutral_n = neutral["stats"]["n_trades"] if neutral else 0

        for gate_name in ["vol_quiet", "vol_active"]:
            g = gates.get(gate_name)
            if g is None:
                continue
            gate_exp = g["stats"]["expectancy_r"]
            gate_n = g["stats"]["n_trades"]
            delta = gate_exp - neutral_exp

            if gate_n < 5:
                verdict = "LOW SAMPLE"
            elif delta > 0.10 and gate_exp > 0:
                verdict = "IMPROVED +"
            elif delta < -0.10:
                verdict = "DEGRADED  -"
            elif abs(delta) <= 0.10:
                verdict = "NEUTRAL   ="
            else:
                verdict = "MIXED     ~"

            print(
                f"  {strat:<16}  {ticker:<5}  {gate_name:<11}  "
                f"{neutral_exp:>+12.3f}  {gate_exp:>+9.3f}  "
                f"{delta:>+7.3f}  {gate_n:>4}  {verdict:<12}"
            )
    print(f"{'=' * w}\n")


# ---------------------------------------------------------------------------
# Table 2: Phase 2 -- 1H Execution Attribution
# ---------------------------------------------------------------------------


def print_phase2_1h_table(rows: list[dict]) -> None:
    """
    Rows: {config, ticker, trigger, data_source, stats, vs_baseline}
    data_source: "1H" or "Daily" or "Daily(fallback)"
    """
    if not rows:
        return
    w = 108
    print(f"\n{'=' * w}")
    print("  FIB6 TRACK B -- 1H EXECUTION ATTRIBUTION")
    print(f"  * = daily fallback (no hourly data available for this instrument)")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Config':<22}  {'Tkr':<4}  {'Data':<7}  "
        f"{'Trd':>4}  {'Win%':>5}  {'ExpR':>7}  "
        f"{'Sharpe':>6}  {'MaxDD':>7}  {'vs_Base':>7}  {'Note':<16}"
    )
    print(hdr)
    print("-" * w)

    prev_ticker = None
    for r in rows:
        s = r["stats"]
        if prev_ticker is not None and prev_ticker != r["ticker"]:
            print()
        prev_ticker = r["ticker"]

        vs_base = r.get("vs_baseline_exp_r")
        vs_str = f"{vs_base:>+7.3f}" if vs_base is not None else f"{'(base)':>7}"
        note = r.get("note", "")

        if s["n_trades"] == 0:
            print(
                f"  {r['config']:<22}  {r['ticker']:<4}  {r.get('data_source', '?'):<7}  "
                f"{'0':>4}  {'--':>5}  {'--':>7}  {'--':>6}  {'--':>7}  {vs_str}  {note}"
            )
            continue
        print(
            f"  {r['config']:<22}  {r['ticker']:<4}  {r.get('data_source', '?'):<7}  "
            f"{s['n_trades']:>4}  {s['win_rate']:>5.1%}  "
            f"{s['expectancy_r']:>+7.3f}  {s['sharpe_r']:>6.3f}  "
            f"{s['max_drawdown']:>7.2%}  {vs_str}  {note}"
        )
    print(f"{'=' * w}\n")


# ---------------------------------------------------------------------------
# Table 3: Phase 3 -- Portfolio Comparison
# ---------------------------------------------------------------------------


def print_phase3_portfolio_table(
    port_results: dict[str, dict],
    single_best: tuple[str, dict],
) -> None:
    """
    port_results: {method_name: portfolio_stats_dict}
    single_best: (ticker, stats)
    """
    w = 90
    print(f"\n{'=' * w}")
    print("  FIB6 TRACK C -- PORTFOLIO CONSTRUCTION")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Config':<28}  {'Trd':>5}  {'Win%':>5}  "
        f"{'ExpR':>7}  {'Sharpe':>6}  {'Sortino':>7}  "
        f"{'PF':>5}  {'MaxDD':>7}"
    )
    print(hdr)
    print("-" * w)

    # Single best benchmark
    sb_ticker, sb_stats = single_best
    if sb_stats:
        label = f"single_best ({sb_ticker})"
        print(
            f"  {label:<28}  {sb_stats.get('n_trades', 0):>5}  "
            f"{'--':>5}  {sb_stats.get('exp_r', 0):>+7.3f}  "
            f"{sb_stats.get('sharpe_r', 0):>6.3f}  {'--':>7}  {'--':>5}  {'--':>7}"
        )
    print()

    for method, pstats in port_results.items():
        if pstats["n_trades"] == 0:
            print(
                f"  {method:<28}  {'0':>5}  {'--':>5}  {'--':>7}  "
                f"{'--':>6}  {'--':>7}  {'--':>5}  {'--':>7}"
            )
            continue
        print(
            f"  {method:<28}  {pstats['n_trades']:>5}  "
            f"{pstats['win_rate']:>5.1%}  {pstats['exp_r']:>+7.3f}  "
            f"{pstats['sharpe_r']:>6.3f}  {pstats['sortino_r']:>7.3f}  "
            f"{pstats['profit_factor']:>5.2f}  {pstats['max_drawdown']:>7.2%}"
        )
        # Print instrument breakdown
        breakdown = pstats.get("breakdown", {})
        if breakdown:
            parts = [
                f"{t}:{d['weight']:.0%}(ExpR={d['exp_r']:+.3f},n={d['n']})"
                for t, d in sorted(breakdown.items())
            ]
            print(f"    -> {' | '.join(parts)}")

    print(f"{'=' * w}\n")


# ---------------------------------------------------------------------------
# Table 4: Phase 4 -- OOS + Friction
# ---------------------------------------------------------------------------


def print_phase4_oos_table(oos_splits: list[dict]) -> None:
    if not oos_splits:
        return
    w = 112
    print(f"\n{'=' * w}")
    print("  FIB6 TRACK D -- OOS VALIDATION")
    print(f"  IS: 2007-2016  |  OOS1: 2017-2022  |  OOS2: 2023+")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Config':<20}  {'Ticker':<5}  {'Period':<8}  "
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
                print(f"  {cfg:<20}  {ticker:<5}  {period_name:<8}  [no data]")
                continue
            if s["n_trades"] == 0:
                print(
                    f"  {cfg:<20}  {ticker:<5}  {period_name:<8}  "
                    f"{s['n_legs']:>5}  {'0':>4}  {'--':>5}  {'--':>7}  "
                    f"{'--':>5}  {'--':>7}  {'--':>8}"
                )
                continue
            adj_r = s.get("adj_expectancy_r", s["expectancy_r"])
            print(
                f"  {cfg:<20}  {ticker:<5}  {period_name:<8}  "
                f"{s['n_legs']:>5}  {s['n_trades']:>4}  "
                f"{s['win_rate']:>5.1%}  {s['expectancy_r']:>+7.3f}  "
                f"{s['profit_factor']:>5.2f}  {s['max_drawdown']:>7.2%}  "
                f"{adj_r:>+8.3f}"
            )
        print()
    print(f"{'=' * w}\n")


def print_phase4_friction_table(friction_rows: list[dict]) -> None:
    if not friction_rows:
        return
    w = 92
    print(f"\n{'=' * w}")
    print("  FIB6 TRACK D -- FRICTION ANALYSIS  (round-trip slippage)")
    print(f"{'=' * w}")
    hdr = (
        f"  {'Config':<22}  {'Ticker':<5}  {'Trd':>4}  "
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
                f"  {r['config']:<22}  {r['ticker']:<5}  {'0':>4}  "
                f"{'--':>8}  {'--':>10}  {'--':>11}  {'--':>10}"
            )
            continue
        survives = "YES" if adj5 > 0.0 else "NO "
        print(
            f"  {r['config']:<22}  {r['ticker']:<5}  {n:>4}  "
            f"{raw:>+8.3f}  {adj5:>+10.3f}  {adj10:>+11.3f}  {survives:>10}"
        )
    print(f"{'=' * w}\n")


def print_robustness_summary(label: str, summary: dict, grid: list[dict]) -> None:
    w = 76
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
# Final deployment classification
# ---------------------------------------------------------------------------

# Classification tiers
REJECT = "REJECT"
MAP_ONLY = "MAP ONLY"
CONFLUENCE_ONLY = "CONFLUENCE ONLY"
STANDALONE_CAND = "STANDALONE CANDIDATE"
DEPLOYMENT_CAND = "DEPLOYMENT CANDIDATE"


def classify_config(
    config_name: str,
    rep_rows: list[dict],  # from phase1 rows for this config
    oos_splits: list[dict],  # from phase4 oos
    rob_summary: Optional[dict],  # from robustness.summarize_grid
    friction_rows: list[dict],  # from phase4 friction
    min_trades: int = 5,
) -> dict:
    """
    Evaluate config against 5 criteria and assign classification.

    Criteria:
      replicates   : positive ExpR on >= 50% of tested instruments (min 3 trades each)
      oos_positive : OOS1 positive on >= 50% of tested instruments
      robust       : >= 60% of grid configs positive (if grid available)
      friction_ok  : >= 67% of instruments survive 5bps slippage
      vol_gate_lift: vol gate improved ExpR vs neutral by >= 0.10R on primary instrument
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

    # 2. OOS
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
        evidence.append(f"oos={oos_positive}/{oos_tested} ({oos_rate:.0%})")

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

    n_met = len(criteria_met)
    if n_met >= 4:
        role = DEPLOYMENT_CAND
    elif n_met >= 3:
        role = STANDALONE_CAND
    elif n_met >= 2:
        role = CONFLUENCE_ONLY
    elif n_met >= 1:
        role = MAP_ONLY
    else:
        role = REJECT

    return {
        "config": config_name,
        "criteria_met": criteria_met,
        "n_criteria": n_met,
        "classification": role,
        "evidence": evidence,
    }


def print_final_classification(classifications: list[dict]) -> None:
    w = 92
    print(f"\n{'#' * w}")
    print("  FIB6 -- SIGNAL ENGINE DEPLOYMENT CLASSIFICATION")
    print(f"{'#' * w}")
    print(f"\n  {'Config':<26}  {'Criteria':<48}  {'Classification'}")
    print(f"  {'-' * 86}")

    tier_order = {
        DEPLOYMENT_CAND: 0,
        STANDALONE_CAND: 1,
        CONFLUENCE_ONLY: 2,
        MAP_ONLY: 3,
        REJECT: 4,
    }
    ranked = sorted(classifications, key=lambda x: tier_order.get(x["classification"], 5))

    prev_tier = None
    for c in ranked:
        tier = c["classification"]
        if prev_tier is not None and tier != prev_tier:
            print()
        prev_tier = tier

        criteria_str = " | ".join(c["criteria_met"]) if c["criteria_met"] else "(none)"
        print(f"  {c['config']:<26}  {criteria_str:<48}  {tier}")
        if c.get("evidence"):
            ev_str = "  ".join(c["evidence"])
            print(f"  {'':26}  Evidence: {ev_str}")

    print(f"\n{'#' * w}")
    print("  DEPLOYMENT CANDIDATES SUMMARY")
    print(f"{'#' * w}")
    deploy = [c for c in ranked if c["classification"] in (DEPLOYMENT_CAND, STANDALONE_CAND)]
    if not deploy:
        print("  No configs reached STANDALONE CANDIDATE or DEPLOYMENT CANDIDATE.")
        print("  Best achieved: " + (ranked[0]["classification"] if ranked else "n/a"))
    else:
        for c in deploy:
            print(f"  {c['config']}: {c['classification']}  [{' | '.join(c['criteria_met'])}]")

    print(f"\n{'#' * w}")
    print("  NEXT HIGHEST-VALUE STEP")
    print(f"{'#' * w}")
    if any(c["classification"] == DEPLOYMENT_CAND for c in ranked):
        print("  1. Build live execution layer with vol regime check at signal bar")
        print("  2. Implement position sizing: risk = vol_regime_gate * base_risk_pct")
        print("  3. Backtest with realistic fill model (VWAP slippage estimate)")
        print("  4. Paper trade 3-6 months: track gate signal accuracy vs live fills")
        print("  5. If paper results hold: scale to small live capital ($25k-$50k)")
    elif any(c["classification"] == STANDALONE_CAND for c in ranked):
        print("  1. Expand OOS window: test 2023-2025 period explicitly")
        print("  2. Add ATR-regime secondary gate to the best standalone candidates")
        print("  3. Re-run with realistic 5bps fill model across all instruments")
        print("  4. If OOS confirms: proceed to paper trading layer")
    else:
        print("  1. The vol gate is directionally promising but not yet sufficient")
        print("  2. Test combined gate: vol_quiet + spy_bull for XLK configs")
        print("  3. Test vol_active + in_discount for QQQ configs")
        print("  4. Consider longer lookback (40-bar vol average) for stability")
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
