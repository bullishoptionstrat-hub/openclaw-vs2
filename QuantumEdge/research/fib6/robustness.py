"""
fib6 robustness: OOS splits, friction, and parameter neighborhood for best configs.
"""

from __future__ import annotations

from typing import Optional

from research.fib2.data import load_daily, load_hourly, build_date_to_1h_range
from research.fib3.detector import find_qualified_legs
from research.fib6.backtester import simulate, friction_adjusted_r
from research.fib6.model import Fib6Config


# ---------------------------------------------------------------------------
# Single period run
# ---------------------------------------------------------------------------


def run_period(
    ticker: str,
    config: Fib6Config,
    start_date: Optional[str],
    end_date: Optional[str],
    spy_daily_full: Optional[dict],
    hourly_bars: Optional[dict] = None,
    date_to_1h: Optional[dict] = None,
) -> Optional[dict]:
    try:
        daily = load_daily(ticker, start_date=start_date, end_date=end_date)
    except (FileNotFoundError, ValueError):
        return None

    legs = find_qualified_legs(
        daily,
        config,
        spy_daily=spy_daily_full if ticker != "SPY" else None,
    )
    results, n_legs, n_skipped, n_reg = simulate(
        legs,
        daily,
        config,
        hourly_bars=hourly_bars,
        date_to_1h=date_to_1h,
        spy_daily=spy_daily_full if ticker != "SPY" else None,
    )
    adj_r = friction_adjusted_r(results, config)

    from research.fib6.analysis import compute_stats

    stats = compute_stats(results, n_legs, n_skipped, n_reg)
    stats["adj_expectancy_r"] = round(sum(adj_r) / len(adj_r), 4) if adj_r else 0.0
    return stats


# ---------------------------------------------------------------------------
# IS / OOS split
# ---------------------------------------------------------------------------


def run_oos_split(
    config_name: str,
    ticker: str,
    config: Fib6Config,
    spy_daily_full: Optional[dict],
    hourly_bars: Optional[dict] = None,
    date_to_1h: Optional[dict] = None,
) -> dict:
    is_start = config.is_start or None
    is_end = config.is_end or None
    oos1_start = config.oos1_start or None
    oos1_end = config.oos1_end or None
    oos2_start = config.oos2_start or None
    oos2_end = config.oos2_end or None

    return {
        "config": config_name,
        "ticker": ticker,
        "is": run_period(ticker, config, is_start, is_end, spy_daily_full, hourly_bars, date_to_1h),
        "oos1": run_period(
            ticker, config, oos1_start, oos1_end, spy_daily_full, hourly_bars, date_to_1h
        ),
        "oos2": run_period(
            ticker, config, oos2_start, oos2_end or None, spy_daily_full, hourly_bars, date_to_1h
        ),
    }


def run_oos_batch(
    configs: dict,
    tickers: list[str],
    spy_daily_full: Optional[dict],
    spy_hourly: Optional[dict] = None,
    spy_date_to_1h: Optional[dict] = None,
) -> list[dict]:
    results = []
    for cfg_name, config in configs.items():
        for ticker in tickers:
            h_bars = spy_hourly if ticker == "SPY" else None
            d_to_1h = spy_date_to_1h if ticker == "SPY" else None
            split = run_oos_split(cfg_name, ticker, config, spy_daily_full, h_bars, d_to_1h)
            results.append(split)
    return results


# ---------------------------------------------------------------------------
# Parameter neighborhood grid
# ---------------------------------------------------------------------------


def build_xlk_quiet_grid() -> list[Fib6Config]:
    """
    Parameter neighborhood around xlk_vol_quiet winner.
    Varies: sweep_min, min_displacement_atr, stop_variant, target_fib.
    3 x 3 x 2 x 2 = 36 configurations.
    """
    from research.fib6.experiments import _make_xlk_quiet_grid_cfg

    configs = []
    for sweep_min in [10.0, 15.0, 20.0]:
        for disp_atr in [2.0, 2.5, 3.0]:
            for stop in ["origin", "fib_786"]:
                for target in [1.272, 1.618]:
                    cfg = _make_xlk_quiet_grid_cfg(sweep_min, disp_atr, stop, target)
                    configs.append(cfg)
    return configs


def build_qqq_active_grid() -> list[Fib6Config]:
    """
    Parameter neighborhood around qqq_vol_active winner.
    Varies: quality_min_score, midzone_tolerance_atr, stop_variant, target_fib.
    3 x 3 x 2 x 2 = 36 configurations.
    """
    from research.fib6.experiments import _make_qqq_active_grid_cfg

    configs = []
    for q_min in [50.0, 60.0, 75.0]:
        for tol in [0.15, 0.20, 0.25]:
            for stop in ["origin", "fib_786"]:
                for target in [1.272, 1.618]:
                    cfg = _make_qqq_active_grid_cfg(q_min, tol, stop, target)
                    configs.append(cfg)
    return configs


def run_grid(
    configs: list,
    ticker: str,
    spy_daily: Optional[dict],
) -> list[dict]:
    """Run a parameter grid for one ticker. Returns list of result dicts."""
    try:
        daily = load_daily(ticker)
    except (FileNotFoundError, ValueError):
        return []

    grid_results = []
    for cfg in configs:
        legs = find_qualified_legs(
            daily,
            cfg,
            spy_daily=spy_daily if ticker != "SPY" else None,
        )
        results, n_legs, n_skipped, n_reg = simulate(
            legs,
            daily,
            cfg,
            spy_daily=spy_daily if ticker != "SPY" else None,
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
                    "vol_gate": getattr(cfg, "vol_regime_gate", "neutral"),
                }
            )
            continue

        r_vals = [t.r_multiple for t in results]
        wins = sum(1 for r in r_vals if r > 0)
        gw = sum(r for r in r_vals if r > 0)
        gl = abs(sum(r for r in r_vals if r < 0))
        pf = gw / gl if gl > 0 else float("inf")
        exp_r = sum(r_vals) / len(r_vals)
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
                "vol_gate": getattr(cfg, "vol_regime_gate", "neutral"),
            }
        )

    return grid_results


def summarize_grid(grid_results: list[dict]) -> dict:
    """Distribution stats for robustness plateau check."""
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

    n_pos = sum(1 for r in exp_rs if r > 0)
    n_gt_010 = sum(1 for r in exp_rs if r > 0.10)
    n_gt_020 = sum(1 for r in exp_rs if r > 0.20)
    return {
        "n_configs": len(grid_results),
        "n_with_trades": n,
        "n_positive": n_pos,
        "n_gt_0.10R": n_gt_010,
        "n_gt_0.20R": n_gt_020,
        "min_exp_r": round(exp_rs[0], 4),
        "q25_exp_r": round(pct(exp_rs, 0.25), 4),
        "median_exp_r": round(pct(exp_rs, 0.50), 4),
        "q75_exp_r": round(pct(exp_rs, 0.75), 4),
        "max_exp_r": round(exp_rs[-1], 4),
        "positive_rate": round(n_pos / n, 4),
    }
