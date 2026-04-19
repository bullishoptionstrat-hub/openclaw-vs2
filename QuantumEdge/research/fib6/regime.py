"""
fib6 regime utilities.

Vol regime gate: check volume at discovery bar vs trailing average.
ATR regime: check ATR ratio at discovery bar (secondary, informational).

All functions are pure, stateless, and operate on pre-loaded numpy arrays.
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Volume ratio
# ---------------------------------------------------------------------------


def compute_vol_ratio(
    volumes: np.ndarray,
    bar: int,
    lookback: int = 20,
) -> float:
    """
    Return volume[bar] / mean(volume[bar-lookback : bar]).

    If insufficient history, returns 1.0 (neutral / don't filter).
    """
    if bar < lookback or bar >= len(volumes):
        return 1.0
    avg = float(np.mean(volumes[bar - lookback : bar]))
    if avg <= 0:
        return 1.0
    return float(volumes[bar]) / avg


def check_vol_gate(
    volumes: np.ndarray,
    bar: int,
    gate: str,
    lookback: int = 20,
    threshold: float = 1.0,
) -> bool:
    """
    Return True if the leg at `bar` passes the vol regime gate.

    gate == "neutral"    -> always True
    gate == "vol_quiet"  -> True if vol_ratio < threshold
    gate == "vol_active" -> True if vol_ratio >= threshold
    """
    if gate == "neutral":
        return True
    ratio = compute_vol_ratio(volumes, bar, lookback)
    if gate == "vol_quiet":
        return ratio < threshold
    if gate == "vol_active":
        return ratio >= threshold
    return True  # Unknown gate type: pass through


# ---------------------------------------------------------------------------
# ATR ratio (informational, not used as pre-filter by default)
# ---------------------------------------------------------------------------


def compute_atr_ratio(
    atr_arr: np.ndarray,
    bar: int,
    lookback: int = 20,
) -> float:
    """
    Return atr[bar] / mean(atr[bar-lookback : bar]).

    Values > 1.0 indicate expanding volatility.
    Returns 1.0 if insufficient data.
    """
    if bar < lookback or bar >= len(atr_arr):
        return 1.0
    cur = atr_arr[bar]
    if np.isnan(cur) or cur <= 0:
        return 1.0
    prior = atr_arr[bar - lookback : bar]
    valid = prior[~np.isnan(prior)]
    if len(valid) < lookback // 2:
        return 1.0
    avg = float(np.mean(valid))
    return cur / avg if avg > 0 else 1.0


# ---------------------------------------------------------------------------
# Regime labeling (for attribution table output)
# ---------------------------------------------------------------------------


def label_vol_regime(vol_ratio: float, threshold: float = 1.0) -> str:
    """Return 'vol_active' or 'vol_quiet' for a given ratio."""
    return "vol_active" if vol_ratio >= threshold else "vol_quiet"


def classify_results_by_regime(
    results: list,
    dates_by_bar: list[str],
    volumes: np.ndarray,
    lookback: int = 20,
    threshold: float = 1.0,
) -> dict[str, list]:
    """
    Split results into vol_quiet / vol_active buckets based on
    volume ratio at each trade's entry bar (discovery bar proxy).

    Returns {"vol_quiet": [results...], "vol_active": [results...]}
    """
    buckets: dict[str, list] = {"vol_quiet": [], "vol_active": []}
    for t in results:
        disc_bar = t.leg.discovery_bar
        ratio = compute_vol_ratio(volumes, disc_bar, lookback)
        key = label_vol_regime(ratio, threshold)
        buckets[key].append(t)
    return buckets
