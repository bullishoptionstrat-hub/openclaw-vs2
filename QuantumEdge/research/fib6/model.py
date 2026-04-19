"""
fib6 data contracts.

Fib6Config -- extends Fib5Config with vol regime gate parameters.
"""

from __future__ import annotations

from dataclasses import dataclass

from research.fib5.model import Fib5Config


@dataclass
class Fib6Config(Fib5Config):
    """
    All Fib5Config fields plus fib6-specific vol regime gate params.

    vol_regime_gate
        Controls which setups are accepted based on volume regime at discovery bar.
        "neutral"    -- no vol filter; same behavior as fib5
        "vol_quiet"  -- only accept setups where vol ratio < threshold
        "vol_active" -- only accept setups where vol ratio >= threshold

    vol_lookback
        Number of bars for trailing volume average. Discovery bar's volume
        is compared against mean(volume[bar-lookback : bar]).

    vol_ratio_threshold
        The ratio pivot between quiet and active.  Default 1.0 means:
        vol_quiet  = volume[bar] / avg_volume < 1.0  (below-average volume)
        vol_active = volume[bar] / avg_volume >= 1.0 (above-average volume)

    n_regime_filtered is tracked separately by the backtester (not stored here).
    """

    # ── Vol regime gate ───────────────────────────────────────────────────────
    vol_regime_gate: str = "neutral"     # "neutral", "vol_quiet", "vol_active"
    vol_lookback: int = 20               # trailing bars for vol average
    vol_ratio_threshold: float = 1.0     # ratio threshold for quiet/active split
