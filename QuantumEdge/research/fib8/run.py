"""
CLI runner for fib8 -- institutional promotion framework.

Usage (from QuantumEdge/ directory):
  python -m research.fib8.run                     # All tracks
  python -m research.fib8.run --track A           # Promotion scoring only
  python -m research.fib8.run --track C D E       # Canonical verdicts only
  python -m research.fib8.run --track F           # Thresholded rotation
  python -m research.fib8.run --track B G         # Forward monitor + signal cards

Track descriptions:
  A  Promotion scoring  -- all 6 candidates scored on 10-criterion framework
  B  Forward monitor   -- paper-trade harness; scan last 60 bars
  C  XLK canonical     -- xlk_vq_baseline vs xlk_vq_tr_786_1618 final verdict
  D  QQQ canonical     -- qqq_completion_vol_active vs qqq_atr_quiet
  E  SPY canonical     -- spy_vol_active_1h_disp promotion test
  F  Rotation v2       -- thresholded rotation with eligibility gates
  G  Signal cards      -- structured cards for PAPER-TRADE CANDIDATE+

Design note:
  Tracks A/C/D/E use pre-computed evidence (no new backtests).
  Track F runs new backtests (thresholded rotation on ROTATION_UNIVERSE).
  Track B runs forward monitor on last 60 bars of current data.
  Track G generates signal cards for all PAPER-TRADE CANDIDATE+ configs.
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
from research.fib7.backtester import simulate
from research.fib7.analysis import compute_stats

from research.fib8.model import PAPER_TRADE, SIGNAL_CARD, LIVE_READY, TIER_ORDER
from research.fib8.experiments import (
    get_candidate_configs,
    get_promotion_evidence,
    CANDIDATE_UNIVERSES,
)
from research.fib8.promotion import (
    promotion_gate,
    print_promotion_table,
    print_promotion_detail,
)
from research.fib8.analysis import (
    xlk_canonical_verdict,
    qqq_canonical_verdict,
    spy_canonical_verdict,
    print_canonical_verdicts,
    print_promotion_summary,
)
from research.fib8.rotation import (
    run_rotation_comparison,
    print_rotation_comparison,
)
from research.fib8.signal_cards import (
    generate_card,
    print_all_cards,
)
from research.fib8.forward_monitor import ForwardMonitor


# ---------------------------------------------------------------------------
# Rotation universe (reuse fib7 definitions)
# ---------------------------------------------------------------------------

ROTATION_UNIVERSE = ["XLK", "QQQ", "IWM", "XLY", "XLF"]


# ---------------------------------------------------------------------------
# Track A: Promotion scoring (no new backtests)
# ---------------------------------------------------------------------------


def track_a_promotion() -> list:
    """
    Score all 6 candidates using pre-computed evidence.
    Returns list[PromotionScore].
    """
    print("\n" + "=" * 70)
    print("  FIB8 TRACK A: PROMOTION SCORING")
    print("=" * 70)

    evidence = get_promotion_evidence()
    scores = promotion_gate(evidence)

    print_promotion_table(scores)

    # Print detail for PAPER-TRADE+ configs
    paper_trade_plus = [
        s for s in scores if TIER_ORDER.index(s.tier) <= TIER_ORDER.index(PAPER_TRADE)
    ]
    print(
        f"\n  {len(paper_trade_plus)} config(s) at PAPER-TRADE or above -- printing detail cards:"
    )
    for ps in paper_trade_plus:
        print_promotion_detail(ps)

    return scores


# ---------------------------------------------------------------------------
# Track B: Forward monitor
# ---------------------------------------------------------------------------


def track_b_forward_monitor(spy_daily: dict, scores: list) -> None:
    """
    Scan last 60 bars for active setups on PAPER-TRADE+ configs.
    """
    print("\n" + "=" * 70)
    print("  FIB8 TRACK B: FORWARD MONITOR (paper-trade harness)")
    print("=" * 70)

    configs = get_candidate_configs()
    paper_plus_names = [
        s.config_name for s in scores if s.tier in (PAPER_TRADE, SIGNAL_CARD, LIVE_READY)
    ]

    if not paper_plus_names:
        print("  No PAPER-TRADE+ configs -- forward monitor skipped.")
        return

    all_setups = []
    for config_name in paper_plus_names:
        cfg = configs.get(config_name)
        if cfg is None:
            continue

        universes = CANDIDATE_UNIVERSES.get(config_name, ["XLK"])
        for ticker in universes[:2]:  # Limit to first 2 instruments per config
            try:
                daily = load_daily(ticker)
            except FileNotFoundError:
                print(f"  [{config_name}] {ticker}: data not found -- skipped")
                continue

            monitor = ForwardMonitor(cfg, ticker, lookback_bars=60)
            setups = monitor.scan(daily, spy_daily)
            all_setups.extend(setups)

    ForwardMonitor.print_ledger(all_setups, title=f"FORWARD MONITOR -- last 60 bars")


# ---------------------------------------------------------------------------
# Track C/D/E: Canonical verdicts (no new backtests)
# ---------------------------------------------------------------------------


def track_cde_canonical(scores: list) -> None:
    """
    Tracks C, D, E: canonical XLK / QQQ / SPY verdicts.
    Uses pre-computed evidence from scores.
    """
    print("\n" + "=" * 70)
    print("  FIB8 TRACKS C/D/E: CANONICAL VERDICTS")
    print("=" * 70)

    score_map = {s.config_name: s for s in scores}

    # XLK (Track C)
    b_score = score_map.get("xlk_vq_baseline")
    c_score = score_map.get("xlk_vq_tr_786_1618")
    if b_score and c_score:
        xlk_v = xlk_canonical_verdict(
            b_score,
            c_score,
            {"expectancy_r": b_score.evidence.get("is_exp_r", 0)},
            {"expectancy_r": c_score.evidence.get("is_exp_r", 0)},
        )
    else:
        xlk_v = {
            "winner": "N/A",
            "rationale": "missing scores",
            "baseline_score": 0,
            "challenger_score": 0,
            "baseline_replication": 0,
            "challenger_replication": 0,
            "expr_delta_on_primary": 0,
        }

    # QQQ (Track D)
    cva_score = score_map.get("qqq_completion_vol_active")
    aq_score = score_map.get("qqq_atr_quiet")
    if cva_score and aq_score:
        qqq_v = qqq_canonical_verdict(cva_score, aq_score)
    else:
        qqq_v = {
            "winner": "N/A",
            "rationale": "missing scores",
            "completion_va_score": 0,
            "atr_quiet_score": 0,
            "completion_va_oos1": None,
            "atr_quiet_oos1": None,
            "completion_va_n": 0,
            "atr_quiet_n": 0,
            "oos2_flag": "",
        }

    # SPY (Track E)
    spy_score_obj = score_map.get("spy_vol_active_1h_disp")
    if spy_score_obj:
        spy_v = spy_canonical_verdict(spy_score_obj)
    else:
        spy_v = {
            "config": "N/A",
            "tier": "N/A",
            "score": 0,
            "status": "missing",
            "blockers_to_signal_card": [],
            "rationale": "missing score",
        }

    print_canonical_verdicts(xlk_v, qqq_v, spy_v)


# ---------------------------------------------------------------------------
# Track F: Thresholded rotation
# ---------------------------------------------------------------------------


def track_f_rotation(spy_daily: dict) -> None:
    """
    Track F: run thresholded rotation comparison on ROTATION_UNIVERSE.
    Uses xlk_vq_baseline config on all instruments.
    """
    print("\n" + "=" * 70)
    print("  FIB8 TRACK F: THRESHOLDED ROTATION v2")
    print("=" * 70)

    configs = get_candidate_configs()
    cfg = configs["xlk_vq_baseline"]

    results_by_ticker = {}
    dates_by_ticker = {}

    for ticker in ROTATION_UNIVERSE:
        try:
            daily = load_daily(ticker)
        except FileNotFoundError:
            print(f"  {ticker}: data not found -- skipped")
            continue

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
        if results:
            results_by_ticker[ticker] = results
            dates_by_ticker[ticker] = daily["dates"]
            stats = compute_stats(results, n_legs, n_skipped, n_reg)
            print(
                f"  {ticker}: n={stats['n_trades']}  ExpR={stats['expectancy_r']:+.4f}  Sharpe={stats['sharpe_r']:.3f}"
            )

    if not results_by_ticker:
        print("  No rotation data -- skipped.")
        return

    comparison = run_rotation_comparison(results_by_ticker, dates_by_ticker)
    print_rotation_comparison(comparison)


# ---------------------------------------------------------------------------
# Track G: Signal cards
# ---------------------------------------------------------------------------


def track_g_signal_cards(scores: list) -> None:
    """
    Track G: generate signal cards for all PAPER-TRADE CANDIDATE+ configs.
    """
    print("\n" + "=" * 70)
    print("  FIB8 TRACK G: SIGNAL CARDS")
    print("=" * 70)

    configs = get_candidate_configs()
    evidence = get_promotion_evidence()
    score_map = {s.config_name: s for s in scores}

    cards = []
    for config_name, ps in score_map.items():
        if ps.tier not in (PAPER_TRADE, SIGNAL_CARD, LIVE_READY):
            continue

        cfg = configs.get(config_name)
        if cfg is None:
            continue

        ev = evidence.get(config_name, {})
        stats = {
            "n_trades": ev.get("primary_n_trades", 0),
            "expectancy_r": ev.get("is_exp_r", 0.0),
            "win_rate": 0.50,  # approximate
            "sharpe_r": ev.get("is_exp_r", 0.0) / 0.60,  # rough estimate
            "max_drawdown": -0.10,  # placeholder
        }
        universe = CANDIDATE_UNIVERSES.get(config_name, ["XLK"])
        card = generate_card(config_name, cfg, stats, ps, ticker_universe=universe)
        cards.append(card)

    print_all_cards(cards)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="fib8 institutional promotion framework")
    parser.add_argument(
        "--track",
        nargs="*",
        default=["A", "C", "D", "E", "F", "G"],
        help="Tracks to run (A B C D E F G). Default: all except B (forward monitor).",
    )
    args = parser.parse_args()
    tracks = set(t.upper() for t in args.track) if args.track else set("ACDEFG")

    # Load SPY (required by most tracks)
    try:
        spy_daily = load_daily("SPY")
        print(f"  SPY loaded: {len(spy_daily['dates'])} bars")
    except FileNotFoundError:
        print("  WARNING: SPY data not found -- some filters may be skipped")
        spy_daily = {
            "dates": [],
            "opens": [],
            "highs": [],
            "lows": [],
            "closes": [],
            "volumes": [],
            "atr": [],
        }

    # Track A: promotion scoring (always run first)
    scores = []
    if "A" in tracks or any(t in tracks for t in "BCDEFG"):
        scores = track_a_promotion()

    if "C" in tracks or "D" in tracks or "E" in tracks:
        track_cde_canonical(scores)

    if "F" in tracks:
        track_f_rotation(spy_daily)

    if "G" in tracks:
        track_g_signal_cards(scores)

    if "B" in tracks:
        track_b_forward_monitor(spy_daily, scores)

    # Final summary
    if scores:
        print_promotion_summary(scores)

    print("\n  fib8 complete.\n")


if __name__ == "__main__":
    main()
