"""
Validity Classification — explicit, rule-based, no hand-waving.

Every run gets one of four labels. The label and the reason are both
machine-readable so they can be filtered and queried in analytics.

Labels (ordered worst to best):
  INVALID_NO_OUTPUT           No CAGR extracted — algorithm crashed before completing
  INVALID_DEPENDENCY_FAILURE  A hard dependency (e.g. Sleeve B fundamentals) was missing
                              and the result does not represent the intended strategy
  PARTIALLY_VALID_MISSING_DATA  Active-sleeve data had gaps but the core result is usable;
                              interpret with caution
  FULLY_VALID                 All active-sleeve data was present; result is trustworthy

Rules are evaluated top-down; the first triggered rule wins.
All triggered warnings (non-fatal) accumulate regardless of final label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from research.results import ResultRecord


# ---------------------------------------------------------------------------
# Label constants — use these everywhere; never raw strings
# ---------------------------------------------------------------------------

FULLY_VALID = "FULLY_VALID"
PARTIALLY_VALID_MISSING_DATA = "PARTIALLY_VALID_MISSING_DATA"
INVALID_DEPENDENCY_FAILURE = "INVALID_DEPENDENCY_FAILURE"
INVALID_NO_OUTPUT = "INVALID_NO_OUTPUT"

_LABEL_RANK = {
    FULLY_VALID: 3,
    PARTIALLY_VALID_MISSING_DATA: 2,
    INVALID_DEPENDENCY_FAILURE: 1,
    INVALID_NO_OUTPUT: 0,
}


@dataclass
class ValidityResult:
    label: str
    reason: str
    warnings: list[str] = field(default_factory=list)

    def is_valid_for_comparison(self) -> bool:
        """True if the result can be included in Sharpe/CAGR comparison tables."""
        return self.label in (FULLY_VALID, PARTIALLY_VALID_MISSING_DATA)

    def rank(self) -> int:
        return _LABEL_RANK.get(self.label, -1)


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

# Known data coverage gaps in the local dataset.
# These are EXPECTED and do not degrade the validity label.
_KNOWN_LATE_STARTERS: dict[str, str] = {
    "VXX": "2018-01-25",  # no data before this date locally
    "XLRE": "2015-10-08",  # sector ETF launched October 2015
    "XLC": "2018-06-19",  # sector ETF launched June 2018
    "SPXU": "2009-06-25",  # 3x inverse launched June 2009
}

# Data failure rate thresholds.  With Sleeve B disabled, Lean's data monitor
# counts universe-selection requests as "failed" even though we intentionally
# skip that universe.  That inflates failure_pct to ~90% on B-disabled runs.
# We only treat failure_pct as a signal when Sleeve B is ENABLED.
_FAIL_PCT_WARN_THRESHOLD = 0.20  # warn if active-sleeve failures exceed this
_FAIL_PCT_INVALID_THRESHOLD = 0.50  # degrade to PARTIALLY_VALID above this


def classify(record: "ResultRecord", overrides: dict) -> ValidityResult:
    """
    Classify a ResultRecord according to explicit rules.

    Parameters
    ----------
    record :
        Parsed result (CAGR, drawdown, data quality fields, etc.)
    overrides :
        The experiment's config overrides dict (as written to experiment_config.json).

    Returns
    -------
    ValidityResult with label, reason, and accumulated warnings.
    """
    warnings: list[str] = []
    b_enabled = overrides.get("ENABLE_SLEEVE_B", False)
    b_behavior = overrides.get(
        "SLEEVE_B_UNAVAILABLE_BEHAVIOR", overrides.get("SLEEVE_B_FALLBACK", "redistribute")
    )

    # ── Rule 1: No output (crash / no CAGR) ─────────────────────────────────
    if record.cagr is None:
        return ValidityResult(
            label=INVALID_NO_OUTPUT,
            reason=(
                "No CAGR found in Lean output (QuantumEdge.json missing or empty). "
                "The algorithm likely crashed before the backtest completed. "
                "Check output/runs/<name>/lean.log for the traceback."
            ),
        )

    # ── Rule 2: Sleeve B dependency failure ─────────────────────────────────
    # Sleeve B requires QuantConnect coarse/fine fundamental data to select
    # Greenblatt stocks.  Without that data the universe selector returns 0
    # stocks on every rebalance, and the B allocation parks in SHY for the
    # entire backtest.  That CAGR is NOT a measure of Sleeve B performance.
    if b_enabled:
        univ_fail = record.universe_failure_pct or 0.0
        if univ_fail > 0.50:
            # Hard failure: >50% of universe requests failed
            warnings.append(
                f"SLEEVE_B_DEPENDENCY_FAILURE: universe_failure_pct={univ_fail:.0%}. "
                f"Fundamental data absent.  Sleeve B allocation parked in SHY/fallback "
                f"for the full backtest period.  Configured behavior: {b_behavior}."
            )
            if b_behavior == "fail":
                return ValidityResult(
                    label=INVALID_DEPENDENCY_FAILURE,
                    reason=(
                        f"Sleeve B enabled, universe_failure_pct={univ_fail:.0%} > 50%, "
                        f"and SLEEVE_B_UNAVAILABLE_BEHAVIOR='fail'. "
                        "Fundamental data (coarse/fine) is required but absent in the "
                        "local dataset.  Source the data or disable Sleeve B."
                    ),
                    warnings=warnings,
                )
            else:
                # Behavior is redistribute/shy/disable — result is partial
                return ValidityResult(
                    label=INVALID_DEPENDENCY_FAILURE,
                    reason=(
                        f"Sleeve B enabled but universe_failure_pct={univ_fail:.0%} > 50%. "
                        "Greenblatt stock selection never occurred.  Reported CAGR "
                        "reflects the fallback behavior, not the intended Sleeve B "
                        f"strategy.  Configured behavior: {b_behavior}."
                    ),
                    warnings=warnings,
                )

        elif univ_fail > 0.10:
            warnings.append(
                f"Sleeve B universe_failure_pct={univ_fail:.0%} — "
                "partial degradation: some rebalance periods selected no stocks."
            )

    # ── Rule 3: Active-sleeve data failure rate ──────────────────────────────
    # With B DISABLED, Lean reports ~90% data failures because the universe
    # data requests are counted as failed.  This is expected behavior, not a
    # signal of data problems in active sleeves.  Skip this check in that case.
    if b_enabled:
        fail_pct = record.data_failure_pct or 0.0
        if fail_pct > _FAIL_PCT_INVALID_THRESHOLD:
            warnings.append(
                f"data_failure_pct={fail_pct:.0%} exceeds {_FAIL_PCT_INVALID_THRESHOLD:.0%} "
                "with Sleeve B enabled."
            )
            return ValidityResult(
                label=PARTIALLY_VALID_MISSING_DATA,
                reason=(
                    f"Overall data failure rate {fail_pct:.0%} with active Sleeve B. "
                    "Some ETF price data may be missing for parts of the backtest period."
                ),
                warnings=warnings,
            )
        elif fail_pct > _FAIL_PCT_WARN_THRESHOLD:
            warnings.append(
                f"data_failure_pct={fail_pct:.0%} — some active-sleeve data gaps present."
            )

    # ── Rule 4: Known late-start tickers ────────────────────────────────────
    # These are expected gaps; note them but do not degrade validity.
    for ticker, start_date in _KNOWN_LATE_STARTERS.items():
        warnings.append(
            f"Known gap: {ticker} data starts {start_date} (local dataset limit). "
            "Pre-date periods fall back gracefully."
        )

    # ── All rules passed ─────────────────────────────────────────────────────
    if warnings:
        return ValidityResult(
            label=FULLY_VALID,
            reason="Active-sleeve data present and validated. See warnings for known gaps.",
            warnings=warnings,
        )
    return ValidityResult(
        label=FULLY_VALID,
        reason="All active-sleeve data present. No data quality issues detected.",
    )
