"""
fib7 data contracts.

Fib7Config -- extends Fib6Config with multi-bar regime measurement controls.

Key additions:
  regime_bar       -- which bar on the leg to measure volume at for the regime gate
                      "discovery"  = volume at discovery_bar (fib6 default)
                      "completion" = volume at completion_bar (fib5 behavior)
                      "anchor"     = volume at anchor_bar (sweep bar)
  atr_regime_gate  -- secondary ATR regime filter (independent of vol gate)
                      "neutral"    = no ATR filter
                      "atr_active" = only setups where ATR ratio >= atr_threshold
                      "atr_quiet"  = only setups where ATR ratio < atr_threshold
  atr_lookback     -- lookback for ATR regime ratio (default 20)
  atr_ratio_threshold -- ATR ratio pivot (default 1.0)
  require_vol_atr_hybrid -- if True, BOTH vol gate AND atr gate must pass
                            (used for QQQ paradox resolution Track B)
"""

from __future__ import annotations

from dataclasses import dataclass

from research.fib6.model import Fib6Config


@dataclass
class Fib7Config(Fib6Config):
    """
    All Fib6Config fields plus fib7-specific multi-bar regime controls.

    regime_bar
        Controls which leg bar is used when computing the vol ratio for
        the vol_regime_gate. This is the key variable for resolving the
        QQQ regime paradox:

          "discovery"   vol[leg.discovery_bar] / avg_vol (fib6 default)
          "completion"  vol[leg.completion_bar] / avg_vol (fib5 behavior)
          "anchor"      vol[leg.anchor_bar] / avg_vol (sweep bar)

        The discovery_bar and completion_bar give opposite regime answers for
        QQQ. This field lets us test all three in a controlled comparison.

    atr_regime_gate / atr_lookback / atr_ratio_threshold
        An ATR-based secondary gate. Independently controls whether setups
        are accepted based on the ATR regime at the discovery bar.

    require_vol_atr_hybrid
        When True, both the vol gate AND the atr gate must pass. This tests
        whether combining vol + ATR regime signals improves filtering.
    """

    # ── Multi-bar regime measurement ─────────────────────────────────────────
    regime_bar: str = "discovery"  # "discovery" | "completion" | "anchor"

    # ── ATR regime gate (secondary) ──────────────────────────────────────────
    atr_regime_gate: str = "neutral"  # "neutral" | "atr_active" | "atr_quiet"
    atr_lookback: int = 20
    atr_ratio_threshold: float = 1.0

    # ── Hybrid mode ──────────────────────────────────────────────────────────
    require_vol_atr_hybrid: bool = False  # True = both vol AND atr gate must pass
