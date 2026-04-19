"""
fib5 parameter robustness testing.

build_xlk_grid()  — parameter neighborhood around XLK winner
build_qqq_grid()  — parameter neighborhood around QQQ winner
run_grid()        — run all configs in a grid for one ticker
summarize_grid()  — distribution stats (plateau vs peak)
"""

from __future__ import annotations

import copy
from typing import Optional

from research.fib2.data import load_daily
from research.fib3.detector import find_qualified_legs
from research.fib5.backtester import simulate, friction_adjusted_r
from research.fib5.model import Fib5Config


# ---------------------------------------------------------------------------
# Grid definitions
# ---------------------------------------------------------------------------


def build_xlk_grid() -> list[dict]:
    """
    Parameter neighborhood around XLK winner:
    sweep_deep + touch_rejection.

    Varies: sweep_min, min_displacement_atr, stop_variant, target_fib.
    3 x 3 x 2 x 2 = 36 configurations.
    """
    configs = []
    for sweep_min in [10.0, 15.0, 20.0]:
        for disp_atr in [2.0, 2.5, 3.0]:
            for stop in ["origin", "fib_786"]:
                for target in [1.272, 1.618]:
                    cfg = Fib5Config()
                    cfg.quality_min_sweep = sweep_min
                    cfg.quality_min_score = 0.0
                    cfg.require_sweep = True
                    cfg.min_displacement_atr = disp_atr
                    cfg.entry_trigger = "touch_rejection"
                    cfg.stop_variant = stop
                    cfg.target_fib = target
                    cfg.name = (
                        f"xlk_g_sw{sweep_min:.0f}_d{disp_atr:.1f}_st{stop[:3]}_tgt{target:.3f}"
                    )
                    configs.append(cfg)
    return configs


def build_qqq_grid() -> list[dict]:
    """
    Parameter neighborhood around QQQ winner:
    midzone_only (Q>=60).

    Varies: quality_min_score, midzone_tolerance_atr, stop_variant, target_fib.
    3 x 3 x 2 x 2 = 36 configurations.
    """
    configs = []
    for q_min in [50.0, 60.0, 75.0]:
        for tol in [0.15, 0.20, 0.25]:
            for stop in ["origin", "fib_786"]:
                for target in [1.272, 1.618]:
                    cfg = Fib5Config()
                    cfg.quality_min_score = q_min
                    cfg.require_sweep = True
                    cfg.min_displacement_atr = 2.0
                    cfg.entry_trigger = "midzone_only"
                    cfg.midzone_tolerance_atr = tol
                    cfg.stop_variant = stop
                    cfg.target_fib = target
                    cfg.name = f"qqq_g_q{q_min:.0f}_tol{tol:.2f}_st{stop[:3]}_tgt{target:.3f}"
                    configs.append(cfg)
    return configs


# ---------------------------------------------------------------------------
# Grid runner
# ---------------------------------------------------------------------------


def run_grid(
    configs: list,
    ticker: str,
    start_date: Optional[str],
    end_date: Optional[str],
    spy_daily: Optional[dict],
) -> list[dict]:
    """
    Run each config in the grid for ticker, return list of result dicts.
    Each dict has: config_name, n_legs, n_trades, win_rate, exp_r, pf, max_dd.
    """
    try:
        daily = load_daily(ticker, start_date=start_date, end_date=end_date)
    except (FileNotFoundError, ValueError):
        return []

    grid_results = []
    for cfg in configs:
        legs = find_qualified_legs(daily, cfg, spy_daily=spy_daily if ticker != "SPY" else None)
        results, n_legs, n_skipped = simulate(
            legs, daily, cfg, spy_daily=spy_daily if ticker != "SPY" else None
        )

        if not results:
            grid_results.append(
                {
                    "config_name": cfg.name,
                    "n_legs": n_legs,
                    "n_trades": 0,
                    "win_rate": 0.0,
                    "exp_r": 0.0,
                    "pf": 0.0,
                    "max_dd": 0.0,
                    "stop": cfg.stop_variant,
                    "target": cfg.target_fib,
                }
            )
            continue

        r_vals = [t.r_multiple for t in results]
        wins = sum(1 for r in r_vals if r > 0)
        gw = sum(r for r in r_vals if r > 0)
        gl = abs(sum(r for r in r_vals if r < 0))
        pf = gw / gl if gl > 0 else float("inf")
        exp_r = sum(r_vals) / len(r_vals)

        # Max drawdown from equity curve
        eq = [results[0].equity_before] + [t.equity_after for t in results]
        peak = eq[0]
        max_dd = 0.0
        for v in eq:
            peak = max(peak, v)
            dd = (v - peak) / peak
            max_dd = min(max_dd, dd)

        grid_results.append(
            {
                "config_name": cfg.name,
                "n_legs": n_legs,
                "n_trades": len(results),
                "win_rate": round(wins / len(results), 4),
                "exp_r": round(exp_r, 4),
                "pf": round(pf, 3),
                "max_dd": round(max_dd, 4),
                "stop": cfg.stop_variant,
                "target": cfg.target_fib,
            }
        )

    return grid_results


def summarize_grid(grid_results: list[dict]) -> dict:
    """
    Summarize grid distribution to test plateau-shaped robustness.
    Returns quantile stats of exp_r.
    """
    if not grid_results:
        return {}

    exp_rs = [r["exp_r"] for r in grid_results if r["n_trades"] >= 5]
    if not exp_rs:
        return {"n_configs": len(grid_results), "n_with_trades": 0}

    exp_rs.sort()
    n = len(exp_rs)

    def pct(vals, p):
        idx = int(p * (len(vals) - 1))
        return vals[idx]

    n_positive = sum(1 for r in exp_rs if r > 0)
    n_gt_010 = sum(1 for r in exp_rs if r > 0.10)
    n_gt_020 = sum(1 for r in exp_rs if r > 0.20)

    return {
        "n_configs": len(grid_results),
        "n_with_trades": n,
        "n_positive": n_positive,
        "n_gt_0.10R": n_gt_010,
        "n_gt_0.20R": n_gt_020,
        "min_exp_r": round(exp_rs[0], 4),
        "q25_exp_r": round(pct(exp_rs, 0.25), 4),
        "median_exp_r": round(pct(exp_rs, 0.50), 4),
        "q75_exp_r": round(pct(exp_rs, 0.75), 4),
        "max_exp_r": round(exp_rs[-1], 4),
        "positive_rate": round(n_positive / n, 4),
    }
