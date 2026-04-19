"""
CLI runner for fib7 -- deployment-oriented signal research.

Usage (from QuantumEdge/ directory):
  python -m research.fib7.run                     # Full run (all tracks)
  python -m research.fib7.run --track A           # XLK hardening only
  python -m research.fib7.run --track B           # QQQ paradox only
  python -m research.fib7.run --track C           # SPY combined only
  python -m research.fib7.run --track D           # Rotation only
  python -m research.fib7.run --track E           # Live spec only (requires A first)
  python -m research.fib7.run --track A B C D E   # All tracks (explicit)

Track descriptions:
  Track A: XLK hardening      -- freeze xlk_vol_quiet, execution neighborhood, friction, OOS
  Track B: QQQ paradox        -- discovery vs completion vs anchor bar vol regime attribution
  Track C: SPY combined       -- vol gate x 1H trigger cross-test on SPY
  Track D: Rotation engine    -- top-1 / top-2 / top-3 selective rotation vs single-best
  Track E: Live spec          -- generate signal spec cards for DEPLOYMENT+ configs
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
from research.fib7.backtester import simulate, friction_adjusted_r
from research.fib7.experiments import (
    TRACK_A_TICKER,
    TRACK_B_TICKER,
    TRACK_C_TICKER,
    ROTATION_UNIVERSE,
    OOS_TICKERS,
    PORTFOLIO_UNIVERSE,
    SLIPPAGE_REALISTIC,
    SLIPPAGE_CONSERVATIVE,
    get_tracka_configs,
    get_trackb_configs,
    get_trackc_configs,
    get_oos_configs,
    build_xlk_tight_grid,
    _base_xlk_vq,
    _base_qqq,
)
from research.fib7.robustness import (
    run_oos_batch,
    run_grid,
    summarize_grid,
)
from research.fib7.rotation import (
    run_top_n_rotation,
    find_single_best,
)
from research.fib7.live_spec import (
    generate_signal_spec,
    print_all_spec_cards,
)
from research.fib7.analysis import (
    compute_stats,
    print_tracka_hardening_table,
    print_trackb_paradox_table,
    print_trackb_paradox_summary,
    print_trackc_spy_combined_table,
    print_trackd_rotation_table,
    print_oos_table,
    print_friction_table,
    print_robustness_summary,
    classify_config,
    print_final_classification,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _run_config(ticker, config, spy_daily, hourly_bars=None, date_to_1h=None):
    """Run one config on one ticker. Returns (results, stats, daily) or (None, None, None)."""
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


def _compute_friction_row(config_name, cfg_name_gate, ticker, results, stats, spy_daily):
    """Build friction row from pre-run results."""
    if stats is None or stats["n_trades"] == 0:
        return {
            "config": config_name,
            "ticker": ticker,
            "n_trades": 0,
            "raw_exp_r": 0.0,
            "adj_exp_r_5bps": 0.0,
            "adj_exp_r_10bps": 0.0,
        }
    raw_r = sum(t.r_multiple for t in results) / len(results)

    # Build friction config variants
    if config_name.startswith("xlk") or config_name.startswith("qqq"):
        base_fn = (
            _base_xlk_vq
            if "xlk" in config_name
            else lambda s: _base_qqq("vol_quiet", "discovery", s)
        )
    else:
        base_fn = _base_xlk_vq

    cfg5 = (
        _base_xlk_vq(SLIPPAGE_REALISTIC)
        if "xlk" in config_name
        else _base_qqq(
            "vol_active" if "active" in config_name else "vol_quiet",
            "completion" if "completion" in config_name else "discovery",
            SLIPPAGE_REALISTIC,
        )
    )
    cfg10 = (
        _base_xlk_vq(SLIPPAGE_CONSERVATIVE)
        if "xlk" in config_name
        else _base_qqq(
            "vol_active" if "active" in config_name else "vol_quiet",
            "completion" if "completion" in config_name else "discovery",
            SLIPPAGE_CONSERVATIVE,
        )
    )

    adj5 = friction_adjusted_r(results, cfg5)
    adj10 = friction_adjusted_r(results, cfg10)
    exp5 = sum(adj5) / len(adj5) if adj5 else 0.0
    exp10 = sum(adj10) / len(adj10) if adj10 else 0.0

    return {
        "config": config_name,
        "ticker": ticker,
        "n_trades": len(results),
        "raw_exp_r": round(raw_r, 4),
        "adj_exp_r_5bps": round(exp5, 4),
        "adj_exp_r_10bps": round(exp10, 4),
    }


# ---------------------------------------------------------------------------
# Track A: XLK deployment hardening
# ---------------------------------------------------------------------------


def track_a_xlk_hardening(spy_daily, hourly_bars, date_to_1h):
    print(f"\n{'=' * 80}")
    print("  FIB7 TRACK A: XLK DEPLOYMENT HARDENING")
    print(f"{'=' * 80}")

    configs = get_tracka_configs()
    rows = []
    results_store = {}

    for cfg_name, config in configs.items():
        for ticker in [TRACK_A_TICKER, "IWM", "XLY", "XLF", "QQQ"]:
            results, stats, daily = _run_config(ticker, config, spy_daily, hourly_bars, date_to_1h)
            if stats is None:
                continue

            adj5 = None
            if results:
                cfg5 = _base_xlk_vq(SLIPPAGE_REALISTIC)
                a5 = friction_adjusted_r(results, cfg5)
                adj5 = sum(a5) / len(a5) if a5 else 0.0

            rows.append(
                {
                    "config": cfg_name,
                    "ticker": ticker,
                    "gate": "vol_quiet",
                    "trigger": getattr(config, "entry_trigger", "?"),
                    "stop": getattr(config, "stop_variant", "?"),
                    "target": getattr(config, "target_fib", 0.0),
                    "stats": stats,
                    "results": results,
                    "adj_exp_r_5bps": round(adj5, 4) if adj5 is not None else None,
                }
            )
            results_store[(cfg_name, ticker)] = (results, stats)

    print_tracka_hardening_table(rows)

    # OOS for baseline
    print(f"\n  Running OOS splits for xlk_vq_baseline...")
    oos_configs = get_oos_configs()
    xlk_oos_configs = {k: v for k, v in oos_configs.items() if k.startswith("xlk")}
    oos_splits = run_oos_batch(
        xlk_oos_configs,
        OOS_TICKERS,
        spy_daily,
        spy_hourly=hourly_bars,
        spy_date_to_1h=date_to_1h,
    )
    print_oos_table(oos_splits, "FIB7 TRACK A -- XLK OOS VALIDATION")

    # Robustness grid
    print(f"\n  Building xlk_vol_quiet tight grid (24 configs on XLK)...")
    xlk_grid = run_grid(build_xlk_tight_grid(), TRACK_A_TICKER, spy_daily)
    xlk_summary = summarize_grid(xlk_grid)
    print_robustness_summary(
        "XLK vol_quiet tight neighborhood (sweep_min x disp_atr x stop x target)",
        xlk_summary,
        xlk_grid,
    )

    return rows, oos_splits, xlk_summary, xlk_grid, results_store


# ---------------------------------------------------------------------------
# Track B: QQQ regime paradox resolution
# ---------------------------------------------------------------------------


def track_b_qqq_paradox(spy_daily):
    print(f"\n{'=' * 80}")
    print("  FIB7 TRACK B: QQQ REGIME PARADOX RESOLUTION")
    print(f"{'=' * 80}")
    print("  Hypothesis: fib5 used completion_bar vol -> vol_active wins.")
    print("  fib6 used discovery_bar vol -> vol_quiet wins.")
    print("  This run tests all three bar types explicitly.")

    configs = get_trackb_configs()
    rows = []

    for cfg_name, config in configs.items():
        results, stats, daily = _run_config(TRACK_B_TICKER, config, spy_daily)
        if stats is None:
            print(f"  SKIP QQQ: data not available")
            continue

        rb = getattr(config, "regime_bar", "discovery")
        gate = getattr(config, "vol_regime_gate", "neutral")
        atr_gate = getattr(config, "atr_regime_gate", "neutral")
        hybrid = getattr(config, "require_vol_atr_hybrid", False)

        display_gate = gate
        if atr_gate != "neutral" and hybrid:
            display_gate = f"{gate}+{atr_gate}"
        elif atr_gate != "neutral":
            display_gate = f"{atr_gate}"

        rows.append(
            {
                "config": cfg_name,
                "ticker": TRACK_B_TICKER,
                "regime_bar": rb,
                "gate": display_gate,
                "stats": stats,
                "results": results,
            }
        )

    print_trackb_paradox_table(rows)
    print_trackb_paradox_summary(rows)

    # OOS for best discovery and completion results
    print(f"\n  Running OOS for QQQ discovery vs completion configs...")
    oos_configs = get_oos_configs()
    qqq_oos_configs = {k: v for k, v in oos_configs.items() if k.startswith("qqq")}
    oos_splits = run_oos_batch(qqq_oos_configs, ["QQQ"], spy_daily)
    print_oos_table(oos_splits, "FIB7 TRACK B -- QQQ OOS VALIDATION")

    return rows, oos_splits


# ---------------------------------------------------------------------------
# Track C: SPY vol gate x 1H trigger
# ---------------------------------------------------------------------------


def track_c_spy_combined(spy_daily, spy_hourly, spy_d_to_1h):
    print(f"\n{'=' * 80}")
    print("  FIB7 TRACK C: SPY VOL GATE x 1H TRIGGER COMBINED")
    print(f"{'=' * 80}")

    configs = get_trackc_configs(spy_has_hourly=spy_hourly is not None)
    rows = []

    # Find baseline: spy_neutral_tr (neutral gate + touch_rejection)
    baseline_exp: dict[str, float] = {}

    for cfg_name, config in configs.items():
        results, stats, daily = _run_config("SPY", config, spy_daily, spy_hourly, spy_d_to_1h)
        if stats is None:
            continue

        gate = getattr(config, "vol_regime_gate", "neutral")
        trigger = getattr(config, "entry_trigger", "?")

        # Track baseline per trigger (neutral gate)
        if gate == "neutral" and trigger not in baseline_exp:
            baseline_exp[trigger] = stats["expectancy_r"]

        vs_base = None
        bl = baseline_exp.get(trigger)
        if bl is not None and gate != "neutral":
            vs_base = stats["expectancy_r"] - bl

        rows.append(
            {
                "config": cfg_name,
                "ticker": "SPY",
                "gate": gate,
                "trigger": trigger,
                "data_source": "1H" if spy_hourly and trigger.startswith("1h_") else "Daily",
                "stats": stats,
                "results": results,
                "vs_baseline_exp_r": vs_base,
            }
        )

    print_trackc_spy_combined_table(rows)

    # Find best combined config
    valid_rows = [r for r in rows if r["stats"]["n_trades"] >= 10]
    if valid_rows:
        best = max(valid_rows, key=lambda r: r["stats"]["expectancy_r"])
        print(f"\n  Best SPY combined config: {best['config']}")
        print(
            f"    Gate={best['gate']}, Trigger={best['trigger']}, "
            f"ExpR={best['stats']['expectancy_r']:+.3f}, "
            f"Sharpe={best['stats']['sharpe_r']:.3f}, "
            f"n={best['stats']['n_trades']}"
        )

    return rows


# ---------------------------------------------------------------------------
# Track D: Selective rotation engine
# ---------------------------------------------------------------------------


def track_d_rotation(tracka_results_store, spy_daily):
    print(f"\n{'=' * 80}")
    print("  FIB7 TRACK D: SELECTIVE TOP-N ROTATION ENGINE")
    print(f"{'=' * 80}")

    # Collect baseline results from Track A across rotation universe
    results_by_ticker = {}
    dates_by_ticker = {}

    baseline_cfg_name = "xlk_vq_baseline"

    for ticker in ROTATION_UNIVERSE:
        key = (baseline_cfg_name, ticker)
        if key in tracka_results_store:
            results, stats = tracka_results_store[key]
            if results:
                results_by_ticker[ticker] = results
                try:
                    daily = load_daily(ticker)
                    dates_by_ticker[ticker] = daily["dates"]
                except FileNotFoundError:
                    pass

    if not results_by_ticker:
        print("  No rotation universe instruments with results. Skipping.")
        return {}

    print(f"  Rotation universe: {list(results_by_ticker.keys())}")
    print(f"  Trade counts: {', '.join(f'{t}={len(r)}' for t, r in results_by_ticker.items())}")

    rotation_results = {}

    for top_n, label in [(1, "top1_rotation"), (2, "top2_rotation"), (3, "top3_rotation")]:
        rstat = run_top_n_rotation(
            results_by_ticker,
            dates_by_ticker,
            top_n=top_n,
            rebalance_every=20,
        )
        rotation_results[label] = rstat

    # Capped top-2
    capped2 = run_top_n_rotation(
        results_by_ticker,
        dates_by_ticker,
        top_n=2,
        max_weight_cap=0.60,
        rebalance_every=20,
    )
    rotation_results["top2_capped60"] = capped2

    # Single best static
    single_best = find_single_best(results_by_ticker)

    # fib6 diluted portfolio reference
    fib6_portfolio_exp_r = 0.037  # Known result from fib6

    print_trackd_rotation_table(rotation_results, single_best, fib6_portfolio_exp_r)

    # Rotation log summary
    for method, rstat in rotation_results.items():
        log = rstat.get("rotation_log", [])
        if log:
            print(f"\n  Last 3 rotation changes for {method}:")
            for entry in log[-3:]:
                print(
                    f"    Trade #{entry['trade_n']}  {entry['date']}  "
                    f"{entry['old_set']} -> {entry['new_set']}"
                )

    return rotation_results


# ---------------------------------------------------------------------------
# Track E: Live signal spec
# ---------------------------------------------------------------------------


def track_e_live_spec(tracka_rows, tracka_oos_splits, xlk_summary, classifications):
    print(f"\n{'=' * 80}")
    print("  FIB7 TRACK E: LIVE SIGNAL READINESS")
    print(f"{'=' * 80}")

    from research.fib7.analysis import DEPLOYMENT_CAND, LIVE_READY

    specs = []
    for cl in classifications:
        if cl["classification"] not in (DEPLOYMENT_CAND, LIVE_READY):
            continue

        cfg_name = cl["config"]

        # Find representative stats from Track A
        rep_rows = [
            r for r in tracka_rows if r["config"] == cfg_name and r["ticker"] == TRACK_A_TICKER
        ]
        if not rep_rows:
            continue
        stats = rep_rows[0]["stats"]

        # Find OOS1 stats
        oos_rows = [
            s
            for s in tracka_oos_splits
            if s["config"] == cfg_name + "_oos" and s["ticker"] == TRACK_A_TICKER
        ]
        oos_stats = oos_rows[0].get("oos1") if oos_rows else None

        # Get config
        from research.fib7.experiments import get_tracka_configs

        all_configs = get_tracka_configs()
        config = all_configs.get(cfg_name)
        if config is None:
            continue

        spec = generate_signal_spec(
            cfg_name,
            config,
            stats,
            oos_stats=oos_stats,
            classification=cl["classification"],
        )
        specs.append(spec)

    print_all_spec_cards(specs)
    return specs


# ---------------------------------------------------------------------------
# Final classification
# ---------------------------------------------------------------------------


def run_final_classification(
    tracka_rows,
    trackb_rows,
    tracka_oos_splits,
    trackb_oos_splits,
    xlk_summary,
    rotation_results,
):
    print(f"\n{'=' * 80}")
    print("  FIB7 PHASE E: DEPLOYMENT CLASSIFICATION")
    print(f"{'=' * 80}")

    classifications = []

    # Track A: xlk_vq_baseline classification
    for cfg_name in ["xlk_vq_baseline"]:
        rep_rows = [r for r in tracka_rows if r["config"] == cfg_name]
        cfg_oos = [s for s in tracka_oos_splits if cfg_name in s["config"]]
        friction_rows = []
        for r in rep_rows:
            results = r.get("results", [])
            if results:
                from research.fib7.experiments import _base_xlk_vq

                cfg5 = _base_xlk_vq(SLIPPAGE_REALISTIC)
                a5 = friction_adjusted_r(results, cfg5)
                cfg10 = _base_xlk_vq(SLIPPAGE_CONSERVATIVE)
                a10 = friction_adjusted_r(results, cfg10)
                exp5 = sum(a5) / len(a5) if a5 else 0.0
                exp10 = sum(a10) / len(a10) if a10 else 0.0
                raw = sum(t.r_multiple for t in results) / len(results) if results else 0.0
                friction_rows.append(
                    {
                        "config": cfg_name,
                        "ticker": r["ticker"],
                        "n_trades": len(results),
                        "raw_exp_r": round(raw, 4),
                        "adj_exp_r_5bps": round(exp5, 4),
                        "adj_exp_r_10bps": round(exp10, 4),
                    }
                )

        # OOS2 data (use same splits but look at oos2 key)
        oos2_splits = cfg_oos  # The same splits contain oos2 key

        cl = classify_config(
            cfg_name,
            rep_rows,
            cfg_oos,
            xlk_summary,
            friction_rows,
            oos2_splits=oos2_splits,
            live_spec_complete=True,  # Track E spec will be generated
        )
        classifications.append(cl)

    # Track B: best QQQ config
    best_qqq_rows = sorted(
        [r for r in trackb_rows if r["stats"]["n_trades"] >= 5],
        key=lambda r: r["stats"]["expectancy_r"],
        reverse=True,
    )
    if best_qqq_rows:
        best_qqq = best_qqq_rows[0]
        qqq_rep_rows = [best_qqq]
        qqq_oos = [s for s in trackb_oos_splits if s["config"] == best_qqq["config"] + "_oos"]
        # Minimal friction for QQQ
        qqq_friction = []
        if best_qqq.get("results"):
            from research.fib7.experiments import _base_qqq

            rbar = best_qqq.get("regime_bar", "discovery")
            gate = best_qqq.get("gate", "vol_quiet")
            cfg5 = _base_qqq(gate, rbar, SLIPPAGE_REALISTIC)
            cfg10 = _base_qqq(gate, rbar, SLIPPAGE_CONSERVATIVE)
            a5 = friction_adjusted_r(best_qqq["results"], cfg5)
            a10 = friction_adjusted_r(best_qqq["results"], cfg10)
            raw = sum(t.r_multiple for t in best_qqq["results"]) / len(best_qqq["results"])
            qqq_friction.append(
                {
                    "config": best_qqq["config"],
                    "ticker": "QQQ",
                    "n_trades": len(best_qqq["results"]),
                    "raw_exp_r": round(raw, 4),
                    "adj_exp_r_5bps": round(sum(a5) / len(a5) if a5 else 0.0, 4),
                    "adj_exp_r_10bps": round(sum(a10) / len(a10) if a10 else 0.0, 4),
                }
            )

        cl = classify_config(
            best_qqq["config"],
            qqq_rep_rows,
            qqq_oos,
            None,  # No robustness grid for QQQ in this run
            qqq_friction,
        )
        classifications.append(cl)

    # Rotation engine
    for method, rstat in rotation_results.items():
        if rstat.get("n_trades", 0) >= 10:
            exp_r = rstat.get("exp_r", 0)
            sharpe = rstat.get("sharpe_r", 0)
            max_dd = rstat.get("max_drawdown", 0)
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
                    "evidence": [f"exp_r={exp_r:+.3f}", f"sharpe={sharpe:.3f}", f"dd={max_dd:.2%}"],
                }
            )

    print_final_classification(classifications)
    return classifications


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args():
    p = argparse.ArgumentParser(description="fib7 deployment-oriented signal research")
    p.add_argument(
        "--track",
        nargs="+",
        choices=["A", "B", "C", "D", "E"],
        default=None,
        help="Tracks to run: A=xlk_hardening, B=qqq_paradox, C=spy_combined, D=rotation, E=live_spec",
    )
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

    tracks = set(args.track) if args.track else {"A", "B", "C", "D", "E"}

    print(f"\n{'#' * 80}")
    print("  FIB7: Deployment-Oriented Signal Research")
    print(f"{'#' * 80}")
    print(f"  Tracks          : {sorted(tracks)}")
    print(f"  Rotation univ   : {', '.join(ROTATION_UNIVERSE)}")
    print(f"  OOS tickers     : {', '.join(OOS_TICKERS)}")
    print(f"  SPY 1H data     : {'loaded' if spy_hourly else 'not available'}")
    print(f"  fib6 ground truth: xlk_vol_quiet = DEPLOYMENT CANDIDATE")
    print(f"  fib6 ground truth: qqq_vol_active = STANDALONE (paradox unresolved)")

    tracka_rows = []
    tracka_oos_splits = []
    xlk_summary = {}
    xlk_grid = []
    tracka_results_store = {}
    trackb_rows = []
    trackb_oos_splits = []
    trackc_rows = []
    rotation_results = {}
    classifications = []

    if "A" in tracks:
        tracka_rows, tracka_oos_splits, xlk_summary, xlk_grid, tracka_results_store = (
            track_a_xlk_hardening(spy_daily, spy_hourly, spy_d_to_1h)
        )

    if "B" in tracks:
        trackb_rows, trackb_oos_splits = track_b_qqq_paradox(spy_daily)

    if "C" in tracks:
        trackc_rows = track_c_spy_combined(spy_daily, spy_hourly, spy_d_to_1h)

    if "D" in tracks:
        if not tracka_results_store and "A" not in tracks:
            print("  Track D requires Track A results. Running Track A first.")
            tracka_rows, tracka_oos_splits, xlk_summary, xlk_grid, tracka_results_store = (
                track_a_xlk_hardening(spy_daily, spy_hourly, spy_d_to_1h)
            )
        rotation_results = track_d_rotation(tracka_results_store, spy_daily)

    # Final classification requires A + B
    if "A" in tracks or "B" in tracks:
        classifications = run_final_classification(
            tracka_rows,
            trackb_rows,
            tracka_oos_splits,
            trackb_oos_splits,
            xlk_summary,
            rotation_results,
        )

    if "E" in tracks:
        track_e_live_spec(tracka_rows, tracka_oos_splits, xlk_summary, classifications)


if __name__ == "__main__":
    main()
