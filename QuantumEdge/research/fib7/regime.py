"""
fib7 regime utilities.

Extends fib6 with:
  1. Multi-bar vol measurement (discovery / completion / anchor bar selection)
  2. ATR regime gate (atr_active / atr_quiet)
  3. Combined vol + ATR hybrid gate

Pure stateless functions operating on numpy arrays.
"""

from __future__ import annotations

import numpy as np

from research.fib6.regime import compute_vol_ratio, check_vol_gate, compute_atr_ratio


# ---------------------------------------------------------------------------
# Bar selector
# ---------------------------------------------------------------------------


def select_regime_bar(leg, regime_bar: str = "discovery") -> int:
    """
    Return the bar index to use for vol regime measurement.

      "discovery"  -> leg.discovery_bar  (fib6 default)
      "completion" -> leg.completion_bar (fib5 behavior)
      "anchor"     -> leg.anchor_bar     (liquidity sweep bar)

    Falls back to discovery_bar for unknown values.
    """
    if regime_bar == "completion":
        return leg.completion_bar
    if regime_bar == "anchor":
        return leg.anchor_bar
    return leg.discovery_bar


# ---------------------------------------------------------------------------
# Multi-bar vol gate
# ---------------------------------------------------------------------------


def check_vol_gate_multibar(
    volumes: np.ndarray,
    leg,
    gate: str,
    regime_bar: str = "discovery",
    lookback: int = 20,
    threshold: float = 1.0,
) -> bool:
    """
    Check vol regime gate at the bar specified by regime_bar.

    gate:       "neutral" | "vol_quiet" | "vol_active"
    regime_bar: "discovery" | "completion" | "anchor"
    """
    if gate == "neutral":
        return True
    bar = select_regime_bar(leg, regime_bar)
    return check_vol_gate(volumes, bar, gate, lookback, threshold)


# ---------------------------------------------------------------------------
# ATR regime gate
# ---------------------------------------------------------------------------


def check_atr_gate(
    atr_arr: np.ndarray,
    bar: int,
    gate: str,
    lookback: int = 20,
    threshold: float = 1.0,
) -> bool:
    """
    Check ATR regime gate at `bar`.

    gate == "neutral"    -> always True
    gate == "atr_active" -> True if atr_ratio >= threshold (expanding ATR)
    gate == "atr_quiet"  -> True if atr_ratio < threshold (compressing ATR)
    """
    if gate == "neutral":
        return True
    ratio = compute_atr_ratio(atr_arr, bar, lookback)
    if gate == "atr_active":
        return ratio >= threshold
    if gate == "atr_quiet":
        return ratio < threshold
    return True


# ---------------------------------------------------------------------------
# Combined gate check
# ---------------------------------------------------------------------------


def check_all_gates(
    volumes: np.ndarray,
    atr_arr: np.ndarray,
    leg,
    config,
) -> tuple[bool, str]:
    """
    Evaluate all fib7 regime gates for a leg.

    Returns (passes, skip_reason):
      passes      -- True if the setup passes all active gates
      skip_reason -- reason string if passes is False, else ""

    Gate precedence:
      1. vol_regime_gate at regime_bar (from config)
      2. atr_regime_gate at discovery_bar
      3. If require_vol_atr_hybrid: both must pass
    """
    vol_gate = getattr(config, "vol_regime_gate", "neutral")
    regime_bar = getattr(config, "regime_bar", "discovery")
    vol_lookback = getattr(config, "vol_lookback", 20)
    vol_threshold = getattr(config, "vol_ratio_threshold", 1.0)

    atr_gate = getattr(config, "atr_regime_gate", "neutral")
    atr_lookback = getattr(config, "atr_lookback", 20)
    atr_threshold = getattr(config, "atr_ratio_threshold", 1.0)
    hybrid = getattr(config, "require_vol_atr_hybrid", False)

    vol_pass = check_vol_gate_multibar(
        volumes, leg, vol_gate, regime_bar, vol_lookback, vol_threshold
    )
    atr_pass = check_atr_gate(atr_arr, leg.discovery_bar, atr_gate, atr_lookback, atr_threshold)

    if hybrid:
        # Both must pass
        if not vol_pass:
            return False, "vol_gate_filtered"
        if not atr_pass:
            return False, "atr_gate_filtered"
        return True, ""

    # Either gate can independently reject (if active)
    if vol_gate != "neutral" and not vol_pass:
        return False, "vol_gate_filtered"
    if atr_gate != "neutral" and not atr_pass:
        return False, "atr_gate_filtered"

    return True, ""


# ---------------------------------------------------------------------------
# Compute vol ratios at all three bar types for attribution
# ---------------------------------------------------------------------------


def compute_all_vol_ratios(volumes: np.ndarray, leg, lookback: int = 20) -> dict:
    """
    Return vol ratios at discovery, completion, and anchor bars.
    Used for the QQQ regime paradox attribution study.
    """
    bars = {
        "discovery": leg.discovery_bar,
        "completion": leg.completion_bar,
        "anchor": leg.anchor_bar,
    }
    return {name: compute_vol_ratio(volumes, bar, lookback) for name, bar in bars.items()}
