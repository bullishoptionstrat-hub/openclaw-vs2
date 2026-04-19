"""
fib8 promotion scoring engine.

10-criterion framework (max 14 usable points).
Pre-computes scores from fib7 results; no new backtests needed here.

score_config()         -- score one config given evidence dict
promotion_gate()       -- batch score all candidates
print_promotion_table()-- formatted ASCII output
"""

from __future__ import annotations

from research.fib8.model import (
    CRITERION_MAX,
    CRITERION_NAMES,
    LIVE_READY,
    MAP_ONLY,
    PAPER_TRADE,
    RESEARCH_ONLY,
    SIGNAL_CARD,
    CONFLUENCE_ONLY,
    TIER_THRESHOLDS,
    PromotionScore,
)


# ---------------------------------------------------------------------------
# Scoring rubrics (pure functions, no I/O)
# ---------------------------------------------------------------------------


def _score_replication(evidence: dict) -> tuple[int, str]:
    """
    % of OOS instruments (5-ticker universe) with positive ExpR.
    0: <50%, 1: 50-75%, 2: >75%
    """
    pct = evidence.get("replication_pct", 0.0)
    if pct > 0.75:
        return 2, f"{pct:.0%} instruments positive (>75%)"
    elif pct >= 0.50:
        return 1, f"{pct:.0%} instruments positive (50-75%)"
    else:
        return 0, f"{pct:.0%} instruments positive (<50%)"


def _score_oos1_quality(evidence: dict) -> tuple[int, str]:
    """
    0: OOS1 negative
    1: OOS1 positive but decays >50% vs IS
    2: OOS1 holds or strengthens
    """
    oos1_r = evidence.get("oos1_exp_r", None)
    is_r = evidence.get("is_exp_r", 0.0)
    oos1_n = evidence.get("oos1_n_trades", 0)

    if oos1_r is None or oos1_n < 3:
        return 0, "OOS1 not run or insufficient trades (<3)"
    if oos1_r <= 0:
        return 0, f"OOS1 negative ({oos1_r:+.3f}R)"
    # Decay check: OOS1 < 50% of IS
    decay_pct = oos1_r / is_r if is_r > 0 else 0.0
    if decay_pct >= 0.5:
        return 2, f"OOS1 {oos1_r:+.3f}R ({decay_pct:.0%} of IS={is_r:+.3f}R) -- holds"
    else:
        return 1, f"OOS1 {oos1_r:+.3f}R ({decay_pct:.0%} of IS={is_r:+.3f}R) -- decays"


def _score_oos2_sufficiency(evidence: dict) -> tuple[int, str]:
    """
    0: <5 trades in OOS2
    1: 5-14 trades positive
    2: >=15 trades positive
    """
    oos2_n = evidence.get("oos2_n_trades", 0)
    oos2_r = evidence.get("oos2_exp_r", None)

    if oos2_n < 5:
        return 0, f"OOS2 only {oos2_n} trades (<5) -- insufficient"
    if oos2_r is None or oos2_r <= 0:
        return 0, f"OOS2 {oos2_n} trades but negative/unknown ExpR"
    if oos2_n >= 15:
        return 2, f"OOS2 {oos2_n} trades, {oos2_r:+.3f}R (>=15)"
    else:
        return 1, f"OOS2 {oos2_n} trades, {oos2_r:+.3f}R (5-14)"


def _score_robustness_plateau(evidence: dict) -> tuple[int, str]:
    """
    % of robustness grid configs with positive ExpR.
    0: <60%, 1: 60-80%, 2: >80%
    """
    pct = evidence.get("grid_positive_pct", None)
    if pct is None:
        return 0, "Robustness grid not run"
    if pct > 0.80:
        return 2, f"{pct:.0%} grid positive (>80%)"
    elif pct >= 0.60:
        return 1, f"{pct:.0%} grid positive (60-80%)"
    else:
        return 0, f"{pct:.0%} grid positive (<60%)"


def _score_friction_survival(evidence: dict) -> tuple[int, str]:
    """
    % of configs positive at 5bps friction.
    0: <67%, 1: 67-90%, 2: >90%
    """
    pct = evidence.get("friction_5bps_positive_pct", None)
    exp_r_5bps = evidence.get("exp_r_at_5bps", None)
    n_variants = evidence.get("friction_n_variants", 1)

    # For single-config friction test
    if pct is None and exp_r_5bps is not None:
        pct = 1.0 if exp_r_5bps > 0 else 0.0

    if pct is None:
        return 0, "Friction test not run"
    if pct > 0.90:
        return 2, f"{pct:.0%} survive 5bps friction (>90%)"
    elif pct >= 0.67:
        return 1, f"{pct:.0%} survive 5bps friction (67-90%)"
    else:
        return 0, f"{pct:.0%} survive 5bps friction (<67%)"


def _score_sample_size(evidence: dict) -> tuple[int, str]:
    """
    Primary period trade count.
    0: <15, 1: 15-29, 2: >=30
    (binary, max 2 per CRITERION_MAX)
    """
    n = evidence.get("primary_n_trades", 0)
    if n >= 30:
        return 2, f"n={n} trades (>=30)"
    elif n >= 15:
        return 1, f"n={n} trades (15-29)"
    else:
        return 0, f"n={n} trades (<15)"


def _score_live_feasibility(evidence: dict) -> tuple[int, str]:
    """
    0: requires intraday data not reliably available
    1: intraday required but feasible (1H data available)
    2: daily-only, clean rules
    """
    needs_intraday = evidence.get("needs_intraday", False)
    intraday_available = evidence.get("intraday_available", False)

    if not needs_intraday:
        return 2, "Daily-only signal -- no intraday dependency"
    elif intraday_available:
        return 1, "Requires 1H data (available but adds operational complexity)"
    else:
        return 0, "Requires intraday data not confirmed available"


def _score_no_hindsight(evidence: dict) -> tuple[int, str]:
    """
    Binary: 0 or 1.
    1 if regime gate is measured at a bar that is known at signal time.
    0 if gate depends on future bar data (hindsight).
    """
    no_hindsight = evidence.get("no_hindsight", True)
    regime_bar = evidence.get("regime_bar", "discovery")
    note = evidence.get("hindsight_note", "")

    if no_hindsight:
        return 1, f"Regime at {regime_bar}_bar -- known at detection time. {note}".strip()
    else:
        return 0, f"Hindsight dependency detected: {note}"


def _score_rule_simplicity(evidence: dict) -> tuple[int, str]:
    """
    Binary: 0 or 1.
    1 if <=6 required conditions (<=3 gives 1, 4-6 gives 1, >6 gives 0).
    Note: plan says <=3 -> 1, 4-6 -> 1 (binary max=1); >6 -> 0
    """
    n_rules = evidence.get("n_required_rules", 4)
    if n_rules <= 6:
        return 1, f"{n_rules} required rules (<=6)"
    else:
        return 0, f"{n_rules} required rules (>6 -- too complex)"


def _score_regime_clarity(evidence: dict) -> tuple[int, str]:
    """
    Binary: 0 or 1.
    1 if gate is defined AND OOS tested.
    (0 = undefined/ambiguous, 0.5 would be defined-but-not-OOS-tested
    -- but since max=1 we only award 1 if both conditions met)
    """
    gate_defined = evidence.get("gate_defined", False)
    gate_oos_tested = evidence.get("gate_oos_tested", False)
    gate_name = evidence.get("vol_gate", "neutral")

    if gate_defined and gate_oos_tested:
        return 1, f"Gate={gate_name} defined and OOS-tested"
    elif gate_defined:
        return 0, f"Gate={gate_name} defined but NOT OOS-tested"
    else:
        return 0, "Gate undefined or neutral (no filtering)"


# ---------------------------------------------------------------------------
# Master scorer
# ---------------------------------------------------------------------------

_SCORERS = {
    "replication": _score_replication,
    "oos1_quality": _score_oos1_quality,
    "oos2_sufficiency": _score_oos2_sufficiency,
    "robustness_plateau": _score_robustness_plateau,
    "friction_survival": _score_friction_survival,
    "sample_size": _score_sample_size,
    "live_feasibility": _score_live_feasibility,
    "no_hindsight": _score_no_hindsight,
    "rule_simplicity": _score_rule_simplicity,
    "regime_clarity": _score_regime_clarity,
}


def score_config(config_name: str, evidence: dict) -> PromotionScore:
    """
    Score one config.

    Parameters
    ----------
    config_name : str
    evidence    : dict -- keys as expected by individual scorers (see above)

    Returns
    -------
    PromotionScore
    """
    breakdown = {}
    notes = {}

    for crit in CRITERION_NAMES:
        scorer = _SCORERS[crit]
        score, note = scorer(evidence)
        # Clamp to max allowed
        score = min(score, CRITERION_MAX[crit])
        breakdown[crit] = score
        notes[crit] = note

    total = sum(breakdown.values())

    # Determine tier
    tier = RESEARCH_ONLY
    for threshold, t in TIER_THRESHOLDS:
        if total >= threshold:
            tier = t
            break

    # Identify blockers (criteria scoring 0)
    blockers = [c for c in CRITERION_NAMES if breakdown[c] == 0]

    # Upgrade path: criteria not at max
    upgrades = []
    for c in CRITERION_NAMES:
        current = breakdown[c]
        max_pts = CRITERION_MAX[c]
        if current < max_pts:
            gain = max_pts - current
            upgrades.append(f"{c} (+{gain} pts): {notes[c]}")

    return PromotionScore(
        config_name=config_name,
        tier=tier,
        total_score=total,
        breakdown=breakdown,
        notes=notes,
        evidence=evidence,
        promotion_blockers=blockers,
        upgrade_path=upgrades[:3],  # Top 3 opportunities
    )


# ---------------------------------------------------------------------------
# Batch promotion gate
# ---------------------------------------------------------------------------


def promotion_gate(candidates: dict[str, dict]) -> list[PromotionScore]:
    """
    Score all candidates.

    Parameters
    ----------
    candidates : {config_name: evidence_dict}

    Returns
    -------
    list[PromotionScore] sorted by total_score descending
    """
    scores = []
    for name, ev in candidates.items():
        ps = score_config(name, ev)
        scores.append(ps)
    scores.sort(key=lambda s: -s.total_score)
    return scores


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def print_promotion_table(scores: list[PromotionScore]) -> None:
    """Print formatted promotion scoring table."""
    w = 100
    print(f"\n{'=' * w}")
    print(f"  FIB8 TRACK A -- PROMOTION SCORING TABLE")
    print(f"  {len(scores)} config(s) evaluated  |  Max possible: 17 pts (4 criteria x2, 6 criteria x1)")
    print(f"{'=' * w}")
    print(
        f"  {'Config':<35} {'Score':>5}  {'Tier':<25} "
        f"{'Repl':>4} {'OOS1':>4} {'OOS2':>4} {'Grid':>4} "
        f"{'Fric':>4} {'N':>4} {'Feas':>4} {'Hint':>4} {'Rule':>4} {'Gate':>4}"
    )
    print(f"  {'-' * 97}")
    for ps in scores:
        b = ps.breakdown
        print(
            f"  {ps.config_name:<35} {ps.total_score:>5}  {ps.tier:<25} "
            f"{b.get('replication', 0):>4} "
            f"{b.get('oos1_quality', 0):>4} "
            f"{b.get('oos2_sufficiency', 0):>4} "
            f"{b.get('robustness_plateau', 0):>4} "
            f"{b.get('friction_survival', 0):>4} "
            f"{b.get('sample_size', 0):>4} "
            f"{b.get('live_feasibility', 0):>4} "
            f"{b.get('no_hindsight', 0):>4} "
            f"{b.get('rule_simplicity', 0):>4} "
            f"{b.get('regime_clarity', 0):>4}"
        )
    print(f"\n  Tier thresholds: LIVE-READY>=13  SIGNAL-CARD 11-12  PAPER-TRADE 9-10")
    print(f"                   CONFLUENCE 7-8  MAP 5-6  RESEARCH <=4")
    print(f"  Criterion max:   Repl=2 OOS1=2 OOS2=2 Grid=2 Fric=2 N=2 Feas=2 Hint=1 Rule=1 Gate=1")
    print(f"{'=' * w}\n")


def print_promotion_detail(ps: PromotionScore) -> None:
    """Print full detail card for one scored config."""
    w = 80
    print(f"\n{'#' * w}")
    print(f"  PROMOTION DETAIL: {ps.config_name}")
    print(f"  Score: {ps.total_score}/17  |  Tier: {ps.tier}")
    print(f"{'#' * w}")
    print(f"\n  Criterion breakdown:")
    for crit in CRITERION_NAMES:
        score = ps.breakdown.get(crit, 0)
        note = ps.notes.get(crit, "")
        max_pts = CRITERION_MAX[crit]
        bar = "#" * score + "." * (max_pts - score)
        print(f"    {crit:<22} [{bar}] {score}/{max_pts}  {note}")

    if ps.promotion_blockers:
        print(f"\n  BLOCKERS (score=0):")
        for b in ps.promotion_blockers:
            print(f"    - {b}")

    if ps.upgrade_path:
        print(f"\n  UPGRADE PATH (top gains available):")
        for u in ps.upgrade_path:
            print(f"    + {u}")
    print(f"\n{'#' * w}\n")
