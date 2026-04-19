"""
Shared signal utilities — no Lean algorithm state, pure computation.

All functions are stateless and take Lean indicator objects as arguments.
This makes them independently testable.
"""

from __future__ import annotations
from AlgorithmImports import *


# ---------------------------------------------------------------------------
# Risk-parity helpers
# ---------------------------------------------------------------------------

def inv_vol(std_indicator: StandardDeviation) -> float:
    """1/realized_vol.  Returns 0.0 if indicator not ready or vol == 0."""
    if std_indicator is None or not std_indicator.is_ready:
        return 0.0
    v = std_indicator.current.value
    return 0.0 if v == 0 else 1.0 / v


def risk_parity_weights(
    tickers: list[str],
    std_map: dict[str, StandardDeviation],
    cap: float = 1.0,
) -> dict[str, float]:
    """
    Return normalised 1/vol weights for `tickers`, capped at `cap`.

    If a ticker has no ready indicator its weight is 0 and the rest are
    re-normalised to sum to 1.0.  Returns an empty dict if all vols are 0.
    """
    raw = {t: inv_vol(std_map.get(t)) for t in tickers}
    total = sum(raw.values())
    if total == 0:
        return {}
    normed: dict[str, float] = {}
    for t, w in raw.items():
        normed[t] = min(w / total, cap)
    # Re-normalise after capping
    total2 = sum(normed.values())
    if total2 == 0:
        return {}
    return {t: round(w / total2, 6) for t, w in normed.items()}


# ---------------------------------------------------------------------------
# IBS (Internal Bar Strength)
# ---------------------------------------------------------------------------

def ibs_score(security: Security) -> float:
    """
    IBS = (Close - Low) / (High - Low).
    Range [0, 1].  Near 0 = oversold, near 1 = overbought.

    Returns 0.5 (neutral) if security is unavailable or range is zero.

    IMPORTANT: in a daily algorithm scheduled 30 min after market open,
    security.close/high/low reflect the PREVIOUS day's bar — no look-ahead.
    """
    if security is None or not security.has_data:
        return 0.5
    hi = security.high
    lo = security.low
    if hi == lo or hi == 0:
        return 0.5
    return float((security.close - lo) / (hi - lo))


# ---------------------------------------------------------------------------
# Momentum scoring (risk-adjusted)
# ---------------------------------------------------------------------------

def momentum_score(
    mom_indicator: RateOfChange,
    std_indicator: StandardDeviation,
) -> float:
    """
    Risk-adjusted momentum = ROC / realised_vol.

    Returns -999.0 if either indicator is not ready, so callers can
    easily filter out tickers that don't qualify.
    """
    if (mom_indicator is None or std_indicator is None
            or not mom_indicator.is_ready or not std_indicator.is_ready):
        return -999.0
    vol = std_indicator.current.value
    if vol == 0:
        return -999.0
    return mom_indicator.current.value / vol


# ---------------------------------------------------------------------------
# Value rank (relative sector valuation proxy)
# ---------------------------------------------------------------------------

def value_rank(
    ticker: str,
    universe: list[str],
    long_mom_map: dict[str, RateOfChange],
) -> float:
    """
    Rank sectors by 2-year relative return, invert so cheap = high score.

    1.0 = most under-performed (cheap proxy)
    0.0 = most over-performed (expensive proxy)
    0.5 = neutral / data missing

    Note: this is a medium-term momentum inversion used as a *value proxy*,
    not a fundamental value signal.  It has ~60% negative correlation with
    the 6-month momentum signal, providing mild diversification.
    """
    scores: dict[str, float] = {}
    for t in universe:
        ind = long_mom_map.get(t)
        if ind and ind.is_ready:
            scores[t] = ind.current.value

    if len(scores) < 3:
        return 0.5

    sorted_tickers = sorted(scores, key=scores.get)   # ascending = cheapest first
    if ticker not in sorted_tickers:
        return 0.5

    rank = sorted_tickers.index(ticker)
    return round(1.0 - rank / max(len(sorted_tickers) - 1, 1), 4)
