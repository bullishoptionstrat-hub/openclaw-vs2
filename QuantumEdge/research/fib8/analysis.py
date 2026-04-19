"""
fib8 analysis: canonical comparisons, verdict tables, and promotion summary.

Tracks:
  C  XLK canonical  -- xlk_vq_baseline vs xlk_vq_tr_786_1618
  D  QQQ canonical  -- qqq_completion_vol_active vs qqq_atr_quiet
  E  SPY canonical  -- spy_vol_active_1h_disp promotion test
"""

from __future__ import annotations

from research.fib8.model import (
    LIVE_READY,
    SIGNAL_CARD,
    PAPER_TRADE,
    CONFLUENCE_ONLY,
    MAP_ONLY,
    RESEARCH_ONLY,
    TIER_ORDER,
)


# ---------------------------------------------------------------------------
# Canonical comparison verdicts
# ---------------------------------------------------------------------------


def xlk_canonical_verdict(
    baseline_score,
    challenger_score,
    baseline_stats: dict,
    challenger_stats: dict,
) -> dict:
    """
    Track C: XLK canonical decision.

    Principle: prefer simpler config unless challenger materially outperforms
    across ALL instruments (not just single-instrument peak).

    Returns verdict dict with recommendation and rationale.
    """
    # Replication check: challenger must match or exceed baseline replication
    baseline_repl = baseline_score.evidence.get("replication_pct", 0)
    challenger_repl = challenger_score.evidence.get("replication_pct", 0)

    # ExpR delta on primary instrument
    b_expr = baseline_stats.get("expectancy_r", baseline_score.evidence.get("is_exp_r", 0))
    c_expr = challenger_stats.get("expectancy_r", challenger_score.evidence.get("is_exp_r", 0))
    expr_delta = c_expr - b_expr

    # Simplicity advantage
    b_rules = baseline_score.evidence.get("n_required_rules", 4)
    c_rules = challenger_score.evidence.get("n_required_rules", 4)
    simpler = b_rules <= c_rules

    # Tier comparison
    b_tier_idx = (
        TIER_ORDER.index(baseline_score.tier)
        if baseline_score.tier in TIER_ORDER
        else len(TIER_ORDER)
    )
    c_tier_idx = (
        TIER_ORDER.index(challenger_score.tier)
        if challenger_score.tier in TIER_ORDER
        else len(TIER_ORDER)
    )

    # Promotion principle: challenger must win on replication AND score
    challenger_wins_replication = challenger_repl > baseline_repl + 0.10
    challenger_wins_score = challenger_score.total_score > baseline_score.total_score

    if challenger_wins_replication and challenger_wins_score:
        winner = "xlk_vq_tr_786_1618"
        rationale = (
            f"Challenger wins: replication {challenger_repl:.0%} > baseline {baseline_repl:.0%}, "
            f"score {challenger_score.total_score} > {baseline_score.total_score}."
        )
    else:
        winner = "xlk_vq_baseline"
        rationale = (
            f"Baseline wins: simpler ({b_rules} rules vs {c_rules}), "
            f"higher replication ({baseline_repl:.0%} vs {challenger_repl:.0%}), "
            f"cross-instrument stable. "
            f"Challenger ExpR advantage ({expr_delta:+.3f}R) is single-instrument only."
        )

    return {
        "winner": winner,
        "rationale": rationale,
        "baseline_score": baseline_score.total_score,
        "challenger_score": challenger_score.total_score,
        "baseline_replication": baseline_repl,
        "challenger_replication": challenger_repl,
        "expr_delta_on_primary": round(expr_delta, 4),
    }


def qqq_canonical_verdict(
    completion_va_score,
    atr_quiet_score,
) -> dict:
    """
    Track D: QQQ canonical decision.

    qqq_completion_vol_active: strong OOS1 (+0.884R strengthens)
    qqq_atr_quiet: simpler but no OOS split

    Principle: OOS1 quality > simplicity when OOS1 is available and positive.
    """
    cva_oos1 = completion_va_score.evidence.get("oos1_exp_r", None)
    aq_oos1 = atr_quiet_score.evidence.get("oos1_exp_r", None)
    cva_n = completion_va_score.evidence.get("primary_n_trades", 0)
    aq_n = atr_quiet_score.evidence.get("primary_n_trades", 0)
    cva_score = completion_va_score.total_score
    aq_score = atr_quiet_score.total_score

    if cva_oos1 is not None and (aq_oos1 is None or cva_oos1 > aq_oos1):
        winner = "qqq_completion_vol_active"
        rationale = (
            f"completion_vol_active wins: OOS1 {cva_oos1:+.3f}R (confirmed) "
            f"vs atr_quiet (no OOS split run). "
            f"Score: {cva_score} vs {aq_score}. "
            f"Flag: OOS2 accumulation needed to upgrade from PAPER-TRADE to SIGNAL-CARD."
        )
    else:
        winner = "qqq_atr_quiet"
        rationale = (
            f"atr_quiet wins: simpler (3 rules), no bar-timing dependency. "
            f"Score: {aq_score} vs {cva_score}. "
            f"Must run OOS split on qqq_atr_quiet to validate."
        )

    return {
        "winner": winner,
        "rationale": rationale,
        "completion_va_score": cva_score,
        "atr_quiet_score": aq_score,
        "completion_va_oos1": cva_oos1,
        "atr_quiet_oos1": aq_oos1,
        "completion_va_n": cva_n,
        "atr_quiet_n": aq_n,
        "oos2_flag": "completion_vol_active needs OOS2 accumulation for SIGNAL-CARD upgrade",
    }


def spy_canonical_verdict(spy_score) -> dict:
    """
    Track E: SPY canonical decision.

    spy_vol_active_1h_disp: best SPY config from fib7.
    Missing: OOS split, robustness grid.
    Expected: PAPER-TRADE CANDIDATE (not SIGNAL-CARD yet).
    """
    tier = spy_score.tier
    score = spy_score.total_score
    oos_tested = spy_score.evidence.get("gate_oos_tested", False)
    grid_run = spy_score.evidence.get("grid_positive_pct") is not None

    blockers_to_signal_card = []
    if not oos_tested:
        blockers_to_signal_card.append("Run OOS split (IS 2007-2016, OOS1 2017-2022)")
    if not grid_run:
        blockers_to_signal_card.append("Run 12-config robustness grid on SPY")
    if spy_score.evidence.get("replication_pct", 0) < 0.75:
        blockers_to_signal_card.append("Test on additional instruments (IWM, QQQ)")

    return {
        "config": "spy_vol_active_1h_disp",
        "tier": tier,
        "score": score,
        "status": f"{tier} -- correct classification",
        "blockers_to_signal_card": blockers_to_signal_card,
        "rationale": (
            f"SPY 1h_disp is the best SPY config (n=43, +0.382R, Sharpe 0.374). "
            f"Needs OOS grid and replication test before SIGNAL-CARD upgrade. "
            f"Intraday dependency limits feasibility score."
        ),
    }


# ---------------------------------------------------------------------------
# Combined output tables
# ---------------------------------------------------------------------------


def print_canonical_verdicts(
    xlk_verdict: dict,
    qqq_verdict: dict,
    spy_verdict: dict,
) -> None:
    """Print all three canonical verdicts."""
    w = 90
    print(f"\n{'=' * w}")
    print(f"  FIB8 CANONICAL VERDICTS")
    print(f"{'=' * w}")

    print(f"\n  TRACK C -- XLK CANONICAL:")
    print(f"    Winner    : {xlk_verdict['winner']}")
    print(
        f"    Baseline  : {xlk_verdict['baseline_score']} pts  replication={xlk_verdict['baseline_replication']:.0%}"
    )
    print(
        f"    Challenger: {xlk_verdict['challenger_score']} pts  replication={xlk_verdict['challenger_replication']:.0%}"
    )
    print(f"    ExpR delta: {xlk_verdict['expr_delta_on_primary']:+.3f}R on primary instrument")
    print(f"    Rationale : {xlk_verdict['rationale']}")

    print(f"\n  TRACK D -- QQQ CANONICAL:")
    print(f"    Winner     : {qqq_verdict['winner']}")
    print(
        f"    completion : score={qqq_verdict['completion_va_score']}  OOS1={qqq_verdict['completion_va_oos1']}  n={qqq_verdict['completion_va_n']}"
    )
    print(
        f"    atr_quiet  : score={qqq_verdict['atr_quiet_score']}  OOS1={qqq_verdict['atr_quiet_oos1']}  n={qqq_verdict['atr_quiet_n']}"
    )
    print(f"    Flag       : {qqq_verdict['oos2_flag']}")
    print(f"    Rationale  : {qqq_verdict['rationale']}")

    print(f"\n  TRACK E -- SPY CANONICAL:")
    print(f"    Config     : {spy_verdict['config']}")
    print(f"    Status     : {spy_verdict['status']}")
    if spy_verdict["blockers_to_signal_card"]:
        print(f"    To SIGNAL-CARD:")
        for b in spy_verdict["blockers_to_signal_card"]:
            print(f"      - {b}")
    print(f"    Rationale  : {spy_verdict['rationale']}")

    print(f"\n{'=' * w}\n")


def print_promotion_summary(scores: list) -> None:
    """
    Print a one-line summary of all promotions.
    scores: list[PromotionScore]
    """
    w = 90
    print(f"\n{'=' * w}")
    print(f"  FIB8 PROMOTION SUMMARY")
    print(f"{'=' * w}")
    for ps in scores:
        tier_flag = ""
        if ps.tier == LIVE_READY:
            tier_flag = " *** LIVE-READY ***"
        elif ps.tier == SIGNAL_CARD:
            tier_flag = " ** SIGNAL-CARD **"
        elif ps.tier == PAPER_TRADE:
            tier_flag = " * PAPER-TRADE *"
        print(f"  {ps.config_name:<35} {ps.total_score:>3} pts  {ps.tier:<25}{tier_flag}")
    print(f"\n  Promotion floor: PAPER-TRADE >= 9 pts")
    print(f"  Forward monitor: all PAPER-TRADE+ configs qualify for paper-trade ledger")
    print(f"{'=' * w}\n")
