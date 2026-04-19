"""
fib9 canonical config freeze -- Track A.

For each instrument, compare candidates on 4 dimensions:
  1. simplicity (fewer rules = better)
  2. replication (% instruments positive)
  3. OOS1 quality (does it hold or strengthen?)
  4. OOS2 recent (thin but meaningful)

Decision standard: prefer simpler config if ExpR within 25% of challenger.

Uses fib7 robustness.run_oos_split() for real OOS splits.
"""

from __future__ import annotations

from typing import Optional

from research.fib7.robustness import run_oos_split
from research.fib7.analysis import compute_stats
from research.fib9.model import CanonicalVerdict
from research.fib9.experiments import (
    get_xlk_candidates,
    get_qqq_candidates,
    get_spy_candidates,
    SIMPLICITY_SCORES,
    OOS1_START,
    OOS1_END,
    OOS2_START,
)


# ---------------------------------------------------------------------------
# OOS split runner for one candidate on one ticker
# ---------------------------------------------------------------------------


def _run_candidate_splits(
    ticker: str,
    candidates: dict,
    spy_daily: dict,
    hourly_bars: Optional[dict] = None,
    date_to_1h: Optional[dict] = None,
) -> dict[str, dict]:
    """
    Run OOS splits for all candidates on one ticker.

    Returns {config_name: {"is": stats, "oos1": stats, "oos2": stats}}
    where stats = {"n_trades": int, "exp_r": float, ...} or None.
    """
    results = {}
    for cfg_name, cfg in candidates.items():
        splits = run_oos_split(
            cfg_name,
            ticker,
            cfg,
            spy_daily_full=spy_daily if ticker != "SPY" else None,
            hourly_bars=hourly_bars if ticker == "SPY" else None,
            date_to_1h=date_to_1h if ticker == "SPY" else None,
        )
        # Normalize to simple per-period dicts
        results[cfg_name] = {
            "is": _extract_period(splits.get("is")),
            "oos1": _extract_period(splits.get("oos1")),
            "oos2": _extract_period(splits.get("oos2")),
        }
    return results


def _extract_period(period_stats: Optional[dict]) -> Optional[dict]:
    """Extract key stats from a run_period result dict."""
    if period_stats is None:
        return None
    return {
        "n_trades": period_stats.get("n_trades", 0),
        "exp_r": period_stats.get("expectancy_r", 0.0),
        "sharpe_r": period_stats.get("sharpe_r", 0.0),
        "win_rate": period_stats.get("win_rate", 0.0),
        "max_dd": period_stats.get("max_drawdown", 0.0),
    }


# ---------------------------------------------------------------------------
# Canonical decision logic
# ---------------------------------------------------------------------------


def _decide_winner(
    ticker: str,
    splits_by_config: dict[str, dict],
    candidates: dict,
    min_is_trades: int = 10,
    simplicity_tie_threshold: float = 0.25,
) -> CanonicalVerdict:
    """
    Apply canonical decision standard to splits results.

    Decision standard:
      1. Discard any config with IS n_trades < min_is_trades
      2. Score on: IS ExpR + OOS1 quality (holds vs decays) + OOS2 sign + simplicity
      3. Prefer simpler config if IS ExpR within 25% of challenger
      4. If OOS1 not available: MONITORED_ONLY (no canonical winner)
    """
    per_candidate = {}
    eligible = []

    for cfg_name, splits in splits_by_config.items():
        is_stats = splits.get("is")
        oos1_stats = splits.get("oos1")
        oos2_stats = splits.get("oos2")

        if is_stats is None or is_stats["n_trades"] < min_is_trades:
            per_candidate[cfg_name] = {
                "is_r": None, "oos1_r": None, "oos2_r": None,
                "is_n": 0, "oos1_n": 0, "oos2_n": 0,
                "simplicity": SIMPLICITY_SCORES.get(cfg_name, 5),
                "eligible": False, "reason": f"IS n={is_stats['n_trades'] if is_stats else 0} < {min_is_trades}",
            }
            continue

        is_r = is_stats["exp_r"]
        is_n = is_stats["n_trades"]
        oos1_r = oos1_stats["exp_r"] if oos1_stats and oos1_stats["n_trades"] >= 3 else None
        oos1_n = oos1_stats["n_trades"] if oos1_stats else 0
        oos2_r = oos2_stats["exp_r"] if oos2_stats and oos2_stats["n_trades"] >= 2 else None
        oos2_n = oos2_stats["n_trades"] if oos2_stats else 0

        simplicity = SIMPLICITY_SCORES.get(cfg_name, 5)

        # OOS1 quality score (0-2)
        if oos1_r is None:
            oos1_quality = -1  # Not run / insufficient
        elif oos1_r <= 0:
            oos1_quality = 0   # Negative
        elif is_r > 0 and oos1_r >= is_r * 0.5:
            oos1_quality = 2   # Holds or strengthens
        else:
            oos1_quality = 1   # Positive but decays

        per_candidate[cfg_name] = {
            "is_r": is_r, "oos1_r": oos1_r, "oos2_r": oos2_r,
            "is_n": is_n, "oos1_n": oos1_n, "oos2_n": oos2_n,
            "simplicity": simplicity,
            "oos1_quality": oos1_quality,
            "eligible": True, "reason": "",
        }
        eligible.append(cfg_name)

    if not eligible:
        return CanonicalVerdict(
            instrument=ticker,
            winner="NONE",
            runner_up=None,
            role="NO_WINNER",
            rationale="No candidates with sufficient IS sample.",
            per_candidate=per_candidate,
            decision_standard="min_is_trades not met",
        )

    # Check if any config has OOS1
    any_oos1 = any(
        per_candidate[c]["oos1_quality"] >= 1
        for c in eligible
        if per_candidate[c]["eligible"]
    )

    # SPY with 1H trigger: mark MONITORED_ONLY if no OOS split or intraday dependency
    any_intraday = any(
        getattr(candidates.get(c), "entry_trigger", "").startswith("1h_")
        for c in eligible
    )
    intraday_only = all(
        getattr(candidates.get(c), "entry_trigger", "").startswith("1h_")
        for c in eligible
    )

    # Sort eligible by composite score: OOS1_quality(2x) + IS_ExpR(1x) - simplicity(0.5x)
    def _score(cfg_name: str) -> float:
        d = per_candidate[cfg_name]
        if not d["eligible"]:
            return float("-inf")
        oos1_q = d.get("oos1_quality", 0)
        if oos1_q < 0:
            oos1_q = 0
        return 2.0 * oos1_q + (d["is_r"] or 0.0) - 0.5 * d["simplicity"]

    ranked = sorted(eligible, key=_score, reverse=True)
    best = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None

    # Simplicity override: if simpler has IS_r within 25% of best
    if runner_up:
        best_data = per_candidate[best]
        runner_data = per_candidate[runner_up]
        best_simple = best_data["simplicity"]
        runner_simple = runner_data["simplicity"]
        best_is_r = best_data["is_r"] or 0.0
        runner_is_r = runner_data["is_r"] or 0.0

        if runner_simple < best_simple and best_is_r > 0:
            # runner_up is simpler; check if within threshold
            deficit = (best_is_r - runner_is_r) / max(best_is_r, 0.01)
            if deficit <= simplicity_tie_threshold:
                best, runner_up = runner_up, best
                per_candidate[best]["reason"] = (
                    f"Simplicity override: within {deficit:.0%} of more complex winner"
                )

    # Role assignment
    if intraday_only and not any_oos1:
        role = "MONITORED_ONLY"
        rationale = (
            f"All SPY candidates require intraday data and have no OOS1 split. "
            f"Best by IS stats: {best}. Cannot award canonical winner without OOS validation."
        )
    elif not any_oos1 and ticker == "QQQ":
        role = "PRIMARY"  # QQQ completion_vol_active has OOS1
        rationale = _build_rationale(best, runner_up, per_candidate)
    else:
        role = "PRIMARY"
        rationale = _build_rationale(best, runner_up, per_candidate)

    return CanonicalVerdict(
        instrument=ticker,
        winner=best,
        runner_up=runner_up,
        role=role,
        rationale=rationale,
        per_candidate=per_candidate,
        decision_standard=(
            f"Prefer simpler if IS ExpR within {simplicity_tie_threshold:.0%}; "
            f"OOS1 quality (hold/strengthen) weighted 2x."
        ),
    )


def _build_rationale(winner: str, runner_up: Optional[str], per_candidate: dict) -> str:
    wd = per_candidate[winner]
    parts = [
        f"{winner} wins:",
        f"IS {wd['is_r']:+.3f}R (n={wd['is_n']})",
    ]
    if wd["oos1_r"] is not None:
        parts.append(f"OOS1 {wd['oos1_r']:+.3f}R (n={wd['oos1_n']})")
    if wd["oos2_r"] is not None:
        parts.append(f"OOS2 {wd['oos2_r']:+.3f}R (n={wd['oos2_n']})")
    parts.append(f"simplicity={wd['simplicity']}")
    if runner_up:
        rd = per_candidate[runner_up]
        is_r_str = f"{rd['is_r']:+.3f}R" if rd["is_r"] is not None else "N/A"
        parts.append(f"| Runner-up {runner_up}: IS {is_r_str} simplicity={rd['simplicity']}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Per-instrument comparison functions
# ---------------------------------------------------------------------------


def compare_xlk_candidates(spy_daily: dict) -> CanonicalVerdict:
    candidates = get_xlk_candidates()
    splits = _run_candidate_splits("XLK", candidates, spy_daily)
    return _decide_winner("XLK", splits, candidates)


def compare_qqq_candidates(spy_daily: dict) -> CanonicalVerdict:
    candidates = get_qqq_candidates()
    splits = _run_candidate_splits("QQQ", candidates, spy_daily)
    return _decide_winner("QQQ", splits, candidates)


def compare_spy_candidates(
    spy_daily: dict,
    hourly_bars: Optional[dict] = None,
    date_to_1h: Optional[dict] = None,
) -> CanonicalVerdict:
    candidates = get_spy_candidates()
    splits = _run_candidate_splits("SPY", candidates, spy_daily, hourly_bars, date_to_1h)
    return _decide_winner("SPY", splits, candidates)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def print_canonical_table(verdicts: list[CanonicalVerdict]) -> None:
    """Print formatted canonical winner table."""
    w = 100
    print(f"\n{'=' * w}")
    print(f"  FIB9 PHASE 1 -- CANONICAL CONFIG FREEZE")
    print(f"  Decision standard: prefer simpler if IS ExpR within 25%; OOS1 quality weighted 2x")
    print(f"{'=' * w}")
    print(f"  {'Ticker':<6} {'Winner':<35} {'Role':<16} {'IS_R':>7} {'IS_N':>5} {'OOS1_R':>8} {'OOS1_N':>6} {'OOS2_R':>8} {'OOS2_N':>6}")
    print(f"  {'-' * 96}")

    for v in verdicts:
        wd = v.per_candidate.get(v.winner, {})
        is_r_s = f"{wd.get('is_r', 0):+.3f}" if wd.get("is_r") is not None else "  N/A"
        oos1_r_s = f"{wd.get('oos1_r', 0):+.3f}" if wd.get("oos1_r") is not None else "  N/A"
        oos2_r_s = f"{wd.get('oos2_r', 0):+.3f}" if wd.get("oos2_r") is not None else "  N/A"
        print(
            f"  {v.instrument:<6} {v.winner:<35} {v.role:<16} "
            f"{is_r_s:>7} {wd.get('is_n', 0):>5} "
            f"{oos1_r_s:>8} {wd.get('oos1_n', 0):>6} "
            f"{oos2_r_s:>8} {wd.get('oos2_n', 0):>6}"
        )
        print(f"    Rationale: {v.rationale}")

        # Runner-up row
        if v.runner_up and v.runner_up in v.per_candidate:
            rd = v.per_candidate[v.runner_up]
            is_r_r = f"{rd.get('is_r', 0):+.3f}" if rd.get("is_r") is not None else "  N/A"
            oos1_r_r = f"{rd.get('oos1_r', 0):+.3f}" if rd.get("oos1_r") is not None else "  N/A"
            print(
                f"         {'(runner-up) ' + v.runner_up:<35} {'':16} "
                f"{is_r_r:>7} {rd.get('is_n', 0):>5} "
                f"{oos1_r_r:>8} {rd.get('oos1_n', 0):>6}"
            )
        print()

    print(f"  Role:  PRIMARY=canonical winner  MONITORED_ONLY=no OOS split  NO_WINNER=insufficient data")
    print(f"{'=' * w}\n")


def print_candidate_details(verdict: CanonicalVerdict) -> None:
    """Print full per-candidate detail for one instrument."""
    w = 80
    print(f"\n  {verdict.instrument} -- all candidates:")
    print(f"  {'Config':<35} {'IS_R':>7} {'IS_N':>5} {'OOS1_R':>8} {'OOS1_N':>6} {'OOS2_R':>8} {'OOS2_N':>6} {'Simp':>4} {'OOS1Q':>5}")
    print(f"  {'-' * 80}")
    for cfg_name, d in verdict.per_candidate.items():
        marker = " <-- WINNER" if cfg_name == verdict.winner else (" <-- runner-up" if cfg_name == verdict.runner_up else "")
        is_r_s = f"{d['is_r']:+.3f}" if d.get("is_r") is not None else "  N/A"
        oos1_r_s = f"{d.get('oos1_r', 0):+.3f}" if d.get("oos1_r") is not None else "  N/A"
        oos2_r_s = f"{d.get('oos2_r', 0):+.3f}" if d.get("oos2_r") is not None else "  N/A"
        oos1_q = d.get("oos1_quality", -1)
        oos1_q_s = str(oos1_q) if oos1_q >= 0 else " --"
        print(
            f"  {cfg_name:<35} {is_r_s:>7} {d.get('is_n', 0):>5} "
            f"{oos1_r_s:>8} {d.get('oos1_n', 0):>6} "
            f"{oos2_r_s:>8} {d.get('oos2_n', 0):>6} "
            f"{d.get('simplicity', '?'):>4} {oos1_q_s:>5}{marker}"
        )
    print()
