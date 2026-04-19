"""
Regime and quality filters for fib2.

All filters operate on already-loaded numpy arrays.
They are evaluated at the discovery_bar of each leg (no lookahead).

Filters:
  spy_bull_regime    — SPY close > 200d SMA at discovery_bar date
  trending           — ATR-expansion proxy: current ATR / 20-bar median ATR
  volume_expansion   — leg completion bar volume > 20-bar avg volume
  premium_discount   — price in lower half (bullish) or upper half (bearish) of recent range
  no_compression     — current ATR > compression_atr_pct * close
"""

from __future__ import annotations

import numpy as np
from typing import Optional


def spy_bull_regime(
    spy_closes: np.ndarray,
    spy_dates: list[str],
    target_date: str,
    sma_period: int = 200,
) -> bool:
    """
    True if SPY close is above its `sma_period`-day SMA on `target_date`.
    Returns True (neutral) if SPY data unavailable at that date.
    """
    # Find the index in spy_dates that is <= target_date
    idx = None
    for i in range(len(spy_dates) - 1, -1, -1):
        if spy_dates[i] <= target_date:
            idx = i
            break
    if idx is None or idx < sma_period - 1:
        return True  # Not enough history — don't filter

    sma = _rolling_mean(spy_closes, sma_period, idx)
    return bool(spy_closes[idx] >= sma)


def is_trending(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    bar: int,
    atr_arr: np.ndarray,
    lookback: int = 20,
    expansion_ratio: float = 1.2,
) -> bool:
    """
    True if current ATR is at least `expansion_ratio` × the median ATR
    over the prior `lookback` bars.  A crude "trending/expanding" proxy.
    """
    if bar < lookback:
        return True  # insufficient history — don't filter
    current_atr = atr_arr[bar]
    if np.isnan(current_atr) or current_atr <= 0:
        return True
    prior_atrs = atr_arr[bar - lookback : bar]
    valid = prior_atrs[~np.isnan(prior_atrs)]
    if len(valid) < lookback // 2:
        return True
    median_atr = float(np.median(valid))
    if median_atr <= 0:
        return True
    return current_atr >= expansion_ratio * median_atr


def volume_expansion_on_leg(
    volumes: np.ndarray,
    completion_bar: int,
    lookback: int = 20,
) -> bool:
    """
    True if volume on the completion bar (HH for bullish, LL for bearish)
    is above the 20-bar average volume ending at completion_bar-1.
    """
    if completion_bar < lookback:
        return True
    avg_vol = float(np.mean(volumes[completion_bar - lookback : completion_bar]))
    if avg_vol <= 0:
        return True
    return bool(volumes[completion_bar] >= avg_vol)


def in_discount(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    bar: int,
    direction: str,
    lookback: int = 60,
) -> bool:
    """
    Premium/discount context.

    For a bullish entry: current price should be in the lower half of the
    `lookback`-bar range (discount).
    For a bearish entry: current price should be in the upper half (premium).
    Returns True (allow trade) if the condition is met, or if insufficient history.
    """
    if bar < lookback:
        return True
    recent_high = float(np.max(highs[bar - lookback : bar + 1]))
    recent_low = float(np.min(lows[bar - lookback : bar + 1]))
    if recent_high <= recent_low:
        return True
    mid = (recent_high + recent_low) / 2.0
    c = closes[bar]
    if direction == "bullish":
        return c <= mid  # discount: price in lower half
    else:
        return c >= mid  # premium: price in upper half


def not_compressed(
    atr_arr: np.ndarray,
    closes: np.ndarray,
    bar: int,
    threshold_pct: float = 0.004,
) -> bool:
    """
    True if ATR/close > threshold_pct (instrument is not in a tight range).
    A compressed instrument has ATR < 0.4% of price by default.
    """
    if bar >= len(atr_arr):
        return True
    atr = atr_arr[bar]
    c = closes[bar]
    if np.isnan(atr) or atr <= 0 or c <= 0:
        return True
    return (atr / c) >= threshold_pct


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _rolling_mean(arr: np.ndarray, period: int, idx: int) -> float:
    start = max(0, idx - period + 1)
    window = arr[start : idx + 1]
    return float(np.mean(window))
