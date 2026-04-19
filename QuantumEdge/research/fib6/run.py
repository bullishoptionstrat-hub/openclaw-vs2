"""
CLI runner for fib6 -- regime-gated, portfolio-aware signal engine.

Usage (from QuantumEdge/ directory):
  python -m research.fib6.run                     # Full run (all phases)
  python -m research.fib6.run --phase 1           # Vol gate only
  python -m research.fib6.run --phase 2           # 1H execution only
  python -m research.fib6.run --phase 3           # Portfolio only
  python -m research.fib6.run --phase 4           # OOS + friction only
  python -m research.fib6.run --phase 1 2 3 4     # All phases (explicit)
  python -m research.fib6.run --ticker XLK QQQ    # Override phase 1 tickers

Phase descriptions:
  Phase 1: Vol regime gate -- xlk_vol_quiet vs baseline, qqq_vol_active vs baseline, spy variants
  Phase 2: 1H execution   -- test all 1H triggers on SPY; daily variants on XLK/QQQ
  Phase 3: Portfolio       -- equal / vol-scaled / capped construction from survivors
  Phase 4: OOS + friction  -- IS/OOS splits and friction adjustment for best configs
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
from research.fib6.backtester import simulate, friction_adjusted_r
from research.fib6.experiments import (
    PHASE1_VOL_TICKERS,
    PHASE2_1H_TICKERS,
    PHASE2_DAILY_TICKERS,
    PORTFOLIO_UNIVERSE,
    OOS_TICKERS,
    SLIPPAGE_REALISTIC,
    SLIPPAGE_CONSERVATIVE,
    get_phase1_configs,
    get_phase2_configs_1h,
    get_phase2_configs_daily,
    get_phase4_configs,
    make_portfolio_config,
)
from research.fib6.robustness import (
    run_oos_batch,
    build_xlk_quiet_grid,
    build_qqq_active_grid,
    run_grid,
    summarize_grid,
)
from research.fib6.portfolio import (
    compute_equal_weights,
    compute_vol_scaled_weights,
    compute_capped_weights,
    build_portfolio,
    find_single_best,
)
from research.fib6.analysis import (
    compute_stats,
    print_phase1_vol_gate_table,
    print_vol_gate_summary,
    print_phase2_1h_table,
    print_phase3_portfolio_table,
    print_phase4_oos_table,
    print_phase4_friction_table,
    print_robustness_summary,
    classify_config,
    print_final_classification,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _run_config(ticker, config, spy_daily, hourly_bars=None, date_to_1h=None):
    """Run one config on one ticker; return (results, stats) or None on missing data."""
    try:
        daily = load_daily(ticker)
    except FileNotFoundError:
        return None, None, None
    legs = find_qualified_legs(
        daily,
        config,
        spy_daily=spy_daily if ticker != "SPY" else None,
    )
    h_bars = hourly_bars if ticker == "SPY" else None
    d_to_1h = date_to_1h if ticker == "SPY" else None
    results, n_legs, n_skipped, n_reg = simulate(
        legs,
        daily,
        config,
        hourly_bars=h_bars,
        date_to_1h=d_to_1h,
        spy_daily=spy_daily if ticker != "SPY" else None,
    )
    stats = compute_stats(results, n_legs, n_skipped, n_reg)
    return results, stats, daily


# ---------------------------------------------------------------------------
# Phase 1: Vol regime gate
# ---------------------------------------------------------------------------


def phase1_vol_gate(tickers, spy_daily, hourly_bars, date_to_1h):
    print(f"\n{'=' * 76}")
    print("  FIB6 PHASE 1: VOL REGIME GATE")
    print(f"{'=' * 76}")

    configs = get_phase1_configs()
    rows = []

    # Map config names to base strategy
    base_map = {
        "xlk_neutral": "xlk",
        "xlk_vol_quiet": "xlk",
        "xlk_vol_active": "xlk",
        "qqq_neutral": "qqq",
        "qqq_vol_active": "qqq",
        "qqq_vol_quiet": "qqq",
        "spy_neutral": "spy",
        "spy_vol_active": "spy",
        "spy_vol_quiet": "spy",
    }
    gate_map = {
        "xlk_neutral": "neutral",
        "xlk_vol_quiet": "vol_quiet",
        "xlk_vol_active": "vol_active",
        "qqq_neutral": "neutral",
        "qqq_vol_active": "vol_active",
        "qqq_vol_quiet": "vol_quiet",
        "spy_neutral": "neutral",
        "spy_vol_active": "vol_active",
        "spy_vol_quiet": "vol_quiet",
    }

    for cfg_name, config in configs.items():
        for ticker in tickers:
            results, stats, daily = _run_config(ticker, config, spy_daily, hourly_bars, date_to_1h)
            if stats is None:
                print(f"  SKIP {ticker}: data not available")
                continue
            rows.append(
                {
                    "config": cfg_name,
                    "base_strategy": base_map.get(cfg_name, cfg_name),
                    "gate": gate_map.get(cfg_name, "neutral"),
                    "ticker": ticker,
                    "stats": stats,
                    "results": results,
                }
            )

    print_phase1_vol_gate_table(rows)
    print_vol_gate_summary(rows)
    return rows


# ---------------------------------------------------------------------------
# Phase 2: 1H execution
# ---------------------------------------------------------------------------


def phase2_1h_execution(spy_daily, spy_hourly, spy_d_to_1h):
    print(f"\n{'=' * 76}")
    print("  FIB6 PHASE 2: 1H EXECUTION LAYER")
    print(f"{'=' * 76}")

    rows = []

    # SPY: real 1H data available
    configs_1h = get_phase2_configs_1h()
    baseline_exp = None
    for cfg_name, config in configs_1h.items():
        results, stats, daily = _run_config("SPY", config, spy_daily, spy_hourly, spy_d_to_1h)
        if stats is None:
            continue

        trigger = config.entry_trigger
        if trigger.startswith("1h_") and spy_hourly is not None:
            data_src = "1H"
            note = ""
        elif trigger.startswith("1h_"):
            data_src = "Daily*"
            note = "1H data not loaded"
        else:
            data_src = "Daily"
            note = "baseline"

        if cfg_name == "spy_daily_baseline":
            baseline_exp = stats["expectancy_r"]

        vs_base = (
            (stats["expectancy_r"] - baseline_exp)
            if baseline_exp is not None and cfg_name != "spy_daily_baseline"
            else None
        )

        rows.append(
            {
                "config": cfg_name,
                "ticker": "SPY",
                "trigger": trigger,
                "data_source": data_src,
                "stats": stats,
                "vs_baseline_exp_r": vs_base,
                "note": note,
            }
        )

    # XLK / QQQ: no hourly data -- daily variants only
    configs_daily = get_phase2_configs_daily()
    baseline_exp_xlk = None
    baseline_exp_qqq = None

    for cfg_name, config in configs_daily.items():
        is_xlk = cfg_name.startswith("xlk_")
        ticker = "XLK" if is_xlk else "QQQ"
        results, stats, daily = _run_config(ticker, config, spy_daily)
        if stats is None:
            continue

        if cfg_name in ("xlk_touch_rejection",) and baseline_exp_xlk is None:
            baseline_exp_xlk = stats["expectancy_r"]
        if cfg_name in ("qqq_midzone_only",) and baseline_exp_qqq is None:
            baseline_exp_qqq = stats["expectancy_r"]

        bl_exp = baseline_exp_xlk if is_xlk else baseline_exp_qqq
        vs_base = None
        if bl_exp is not None:
            baseline_cfg = "xlk_touch_rejection" if is_xlk else "qqq_midzone_only"
            vs_base = (stats["expectancy_r"] - bl_exp) if cfg_name != baseline_cfg else None

        rows.append(
            {
                "config": cfg_name,
                "ticker": ticker,
                "trigger": config.entry_trigger,
                "data_source": "Daily(vg)",
                "stats": stats,
                "vs_baseline_exp_r": vs_base,
                "note": "vol-gated daily"
                if cfg_name != ("xlk_touch_rejection" if is_xlk else "qqq_midzone_only")
                else "baseline(vol-gated)",
            }
        )

    print_phase2_1h_table(rows)
    return rows


# ---------------------------------------------------------------------------
# Phase 3: Portfolio construction
# ---------------------------------------------------------------------------


def phase3_portfolio(phase1_rows, spy_daily):
    print(f"\n{'=' * 76}")
    print("  FIB6 PHASE 3: PORTFOLIO CONSTRUCTION")
    print(f"{'=' * 76}")

    # Collect results for portfolio instruments using best gated configs
    # xlk_vol_quiet on XLK/IWM/XLY/XLF; qqq_vol_active on QQQ
    vol_gate_map = {
        "XLK": ("xlk", "vol_quiet"),
        "QQQ": ("qqq", "vol_active"),
        "IWM": ("xlk", "vol_quiet"),  # xlk_style replicates on IWM
        "XLY": ("xlk", "vol_quiet"),
        "XLF": ("xlk", "vol_quiet"),
    }

    results_by_ticker = {}
    dates_by_ticker = {}

    for ticker in PORTFOLIO_UNIVERSE:
        style, gate = vol_gate_map.get(ticker, ("xlk", "vol_quiet"))
        cfg_name = f"{style}_{gate}"

        # Find in phase1 rows
        matching = [r for r in phase1_rows if r["config"] == cfg_name and r["ticker"] == ticker]
        if matching and matching[0]["results"]:
            results_by_ticker[ticker] = matching[0]["results"]
            try:
                daily = load_daily(ticker)
                dates_by_ticker[ticker] = daily["dates"]
            except FileNotFoundError:
                pass

    if not results_by_ticker:
        print("  No portfolio instruments with results. Skipping portfolio phase.")
        return {}

    print(f"  Portfolio instruments: {list(results_by_ticker.keys())}")
    print(f"  Trade counts: {', '.join(f'{t}={len(r)}' for t, r in results_by_ticker.items())}")

    # Compute weights
    eq_weights = compute_equal_weights(list(results_by_ticker.keys()))
    vs_weights = compute_vol_scaled_weights(results_by_ticker, min_trades=5)
    cap_weights = compute_capped_weights(results_by_ticker, max_weight=0.40, min_trades=5)

    port_results = {}

    for method, weights in [
        ("equal_weight_5inst", eq_weights),
        ("vol_scaled_5inst", vs_weights),
        ("capped_40pct_5inst", cap_weights),
    ]:
        if not weights:
            continue
        pstats = build_portfolio(
            results_by_ticker,
            dates_by_ticker,
            weights,
        )
        port_results[method] = pstats

    # Single best benchmark
    single_best = find_single_best(results_by_ticker)

    print_phase3_portfolio_table(port_results, single_best)
    return port_results


# ---------------------------------------------------------------------------
# Phase 4: OOS + friction
# ---------------------------------------------------------------------------


def phase4_oos_friction(spy_daily, spy_hourly, spy_d_to_1h):
    print(f"\n{'=' * 76}")
    print("  FIB6 PHASE 4: OOS VALIDATION + FRICTION")
    print(f"{'=' * 76}")

    # OOS splits for best configs
    oos_configs = {
        "xlk_vol_quiet": __import__("research.fib6.experiments", fromlist=["_base_xlk"])._base_xlk(
            "vol_quiet"
        ),
        "qqq_vol_active": __import__("research.fib6.experiments", fromlist=["_base_qqq"])._base_qqq(
            "vol_active"
        ),
        "xlk_neutral": __import__("research.fib6.experiments", fromlist=["_base_xlk"])._base_xlk(
            "neutral"
        ),
        "qqq_neutral": __import__("research.fib6.experiments", fromlist=["_base_qqq"])._base_qqq(
            "neutral"
        ),
    }

    oos_splits = run_oos_batch(
        oos_configs,
        OOS_TICKERS,
        spy_daily,
        spy_hourly=spy_hourly,
        spy_date_to_1h=spy_d_to_1h,
    )
    print_phase4_oos_table(oos_splits)

    # Friction analysis
    friction_rows = []
    for cfg_name, base_cfg in [
        ("xlk_vol_quiet", oos_configs["xlk_vol_quiet"]),
        ("qqq_vol_active", oos_configs["qqq_vol_active"]),
    ]:
        for ticker in ["XLK", "QQQ", "IWM", "XLY", "XLF"]:
            results, stats, _ = _run_config(ticker, base_cfg, spy_daily)
            if stats is None or stats["n_trades"] == 0:
                friction_rows.append(
                    {
                        "config": cfg_name,
                        "ticker": ticker,
                        "n_trades": 0,
                        "raw_exp_r": 0.0,
                        "adj_exp_r_5bps": 0.0,
                        "adj_exp_r_10bps": 0.0,
                    }
                )
                continue
            raw_r = sum(t.r_multiple for t in results) / len(results)

            from research.fib6.experiments import _base_xlk, _base_qqq

            if cfg_name.startswith("xlk"):
                cfg5 = _base_xlk("vol_quiet", SLIPPAGE_REALISTIC)
                cfg10 = _base_xlk("vol_quiet", SLIPPAGE_CONSERVATIVE)
            else:
                cfg5 = _base_qqq("vol_active", SLIPPAGE_REALISTIC)
                cfg10 = _base_qqq("vol_active", SLIPPAGE_CONSERVATIVE)

            adj5 = friction_adjusted_r(results, cfg5)
            adj10 = friction_adjusted_r(results, cfg10)
            exp5 = sum(adj5) / len(adj5) if adj5 else 0.0
            exp10 = sum(adj10) / len(adj10) if adj10 else 0.0

            friction_rows.append(
                {
                    "config": cfg_name,
                    "ticker": ticker,
                    "n_trades": len(results),
                    "raw_exp_r": round(raw_r, 4),
                    "adj_exp_r_5bps": round(exp5, 4),
                    "adj_exp_r_10bps": round(exp10, 4),
                }
            )

    print_phase4_friction_table(friction_rows)

    # Robustness grids
    print(f"\n{'=' * 76}")
    print("  FIB6 PHASE 4: PARAMETER ROBUSTNESS")
    print(f"{'=' * 76}")

    print("  Building xlk_vol_quiet grid (36 configs on XLK)...")
    xlk_grid = run_grid(build_xlk_quiet_grid(), "XLK", spy_daily)
    xlk_summary = summarize_grid(xlk_grid)
    print_robustness_summary(
        "XLK vol_quiet neighborhood (sweep_min x disp_atr x stop x target)",
        xlk_summary,
        xlk_grid,
    )

    print("\n  Building qqq_vol_active grid (36 configs on QQQ)...")
    qqq_grid = run_grid(build_qqq_active_grid(), "QQQ", spy_daily)
    qqq_summary = summarize_grid(qqq_grid)
    print_robustness_summary(
        "QQQ vol_active neighborhood (q_min x tol x stop x target)",
        qqq_summary,
        qqq_grid,
    )

    return oos_splits, friction_rows, xlk_summary, qqq_summary, xlk_grid, qqq_grid


# ---------------------------------------------------------------------------
# Final classification
# ---------------------------------------------------------------------------


def run_final_classification(
    phase1_rows, oos_splits, friction_rows, xlk_rob, qqq_rob, port_results
):
    print(f"\n{'=' * 76}")
    print("  FIB6 PHASE E: DEPLOYMENT CLASSIFICATION")
    print(f"{'=' * 76}")

    classifications = []

    for cfg_name in ["xlk_vol_quiet", "xlk_neutral", "qqq_vol_active", "qqq_neutral"]:
        rep_rows = [r for r in phase1_rows if r["config"] == cfg_name]
        cfg_oos = [s for s in oos_splits if s["config"] == cfg_name]
        cfg_fric = [r for r in friction_rows if r["config"] == cfg_name]

        if cfg_name.startswith("xlk"):
            rob = xlk_rob
        elif cfg_name.startswith("qqq"):
            rob = qqq_rob
        else:
            rob = None

        cl = classify_config(cfg_name, rep_rows, cfg_oos, rob, cfg_fric)
        classifications.append(cl)

    # Add portfolio as a concept entry
    for method, pstats in port_results.items():
        if pstats.get("n_trades", 0) >= 10:
            exp_r = pstats.get("exp_r", 0)
            sharpe = pstats.get("sharpe_r", 0)
            max_dd = pstats.get("max_drawdown", 0)
            # Simplified portfolio classification
            criteria = []
            if exp_r > 0.05:
                criteria.append("positive_exp_r")
            if sharpe > 0.3:
                criteria.append("positive_sharpe")
            if max_dd > -0.20:
                criteria.append("drawdown_ok")

            n_met = len(criteria)
            if n_met >= 3:
                role = "DEPLOYMENT CANDIDATE"
            elif n_met >= 2:
                role = "STANDALONE CANDIDATE"
            elif n_met >= 1:
                role = "CONFLUENCE ONLY"
            else:
                role = "MAP ONLY"

            classifications.append(
                {
                    "config": method,
                    "criteria_met": criteria,
                    "n_criteria": n_met,
                    "classification": role,
                    "evidence": [
                        f"exp_r={exp_r:+.3f}",
                        f"sharpe={sharpe:.3f}",
                        f"dd={max_dd:.2%}",
                    ],
                }
            )

    print_final_classification(classifications)
    return classifications


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args():
    p = argparse.ArgumentParser(description="fib6 regime-gated signal engine")
    p.add_argument(
        "--phase",
        type=int,
        nargs="+",
        default=None,
        help="Phases to run: 1=vol_gate, 2=1H_exec, 3=portfolio, 4=oos_friction",
    )
    p.add_argument("--ticker", nargs="+", default=None, help="Override phase 1 ticker list")
    return p.parse_args()


def main():
    args = parse_args()

    # Load SPY data once
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

    phases = set(args.phase) if args.phase else {1, 2, 3, 4}
    p1_tickers = [t.upper() for t in args.ticker] if args.ticker else PHASE1_VOL_TICKERS

    print(f"\n{'#' * 76}")
    print("  FIB6: Regime-Gated Signal Engine")
    print(f"{'#' * 76}")
    print(f"  Phases          : {sorted(phases)}")
    print(f"  Phase 1 tickers : {', '.join(p1_tickers)}")
    print(f"  Portfolio univ  : {', '.join(PORTFOLIO_UNIVERSE)}")
    print(f"  SPY 1H data     : {'loaded' if spy_hourly else 'not available'}")
    print(f"  Note: XLK/QQQ have no hourly data -- 1H triggers use daily fallback")

    phase1_rows = []
    port_results = {}
    oos_splits = []
    friction_rows = []
    xlk_rob, qqq_rob = {}, {}
    xlk_grid, qqq_grid = [], []

    if 1 in phases:
        phase1_rows = phase1_vol_gate(p1_tickers, spy_daily, spy_hourly, spy_d_to_1h)

    if 2 in phases:
        phase2_1h_execution(spy_daily, spy_hourly, spy_d_to_1h)

    if 3 in phases:
        port_results = phase3_portfolio(phase1_rows, spy_daily)

    if 4 in phases:
        oos_splits, friction_rows, xlk_rob, qqq_rob, xlk_grid, qqq_grid = phase4_oos_friction(
            spy_daily, spy_hourly, spy_d_to_1h
        )

    # Final classification runs if all phases completed
    if phases >= {1, 4}:
        run_final_classification(
            phase1_rows,
            oos_splits,
            friction_rows,
            xlk_rob,
            qqq_rob,
            port_results,
        )


if __name__ == "__main__":
    main()
