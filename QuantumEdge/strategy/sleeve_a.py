"""
Sleeve A — Sector Momentum + Value Tilt

Alpha source: cross-sectional momentum across 11 US SPDR sector ETFs,
blended with a 2-year relative-return value rank.

Weights:  top-N sectors by composite score → risk-parity sizing.
Fallback: SHY if regime is defensive or no sector has positive score.
"""

from __future__ import annotations
from AlgorithmImports import *
from algorithm.config import (
    SECTORS,
    SECTOR_TOP_N,
    MOMENTUM_DAYS,
    VALUE_BLEND,
    VALUE_LOOKBACK,
    MAX_POSITION,
    FALLBACK_ASSET,
)
from strategy.signals import momentum_score, value_rank, risk_parity_weights


class SleeveA:
    """
    Sector momentum sleeve.

    Args:
        algorithm:    parent QCAlgorithm (for logging only)
        sym_map:      ticker → Symbol
        mom_map:      ticker → RateOfChange (MOMENTUM_DAYS)
        std_map:      ticker → StandardDeviation (RISK_VOL_LB)
        long_mom_map: ticker → RateOfChange (VALUE_LOOKBACK)
        allocation:   fraction of total portfolio (effective, already scaled)
    """

    def __init__(
        self,
        algorithm: QCAlgorithm,
        sym_map: dict[str, Symbol],
        mom_map: dict[str, RateOfChange],
        std_map: dict[str, StandardDeviation],
        long_mom_map: dict[str, RateOfChange],
        allocation: float,
    ):
        self._algo = algorithm
        self._sym = sym_map
        self._mom = mom_map
        self._std = std_map
        self._long_mom = long_mom_map
        self._alloc = allocation

    # ------------------------------------------------------------------

    def targets(self, equity_regime: bool) -> dict[str, float]:
        """
        Return ticker → portfolio weight for Sleeve A.

        If not in equity regime → all allocation to FALLBACK_ASSET.
        If no sector has positive composite score → all to FALLBACK_ASSET.
        """
        if not equity_regime:
            return {FALLBACK_ASSET: self._alloc}

        scores = self._score_sectors()
        positive = {t: s for t, s in scores.items() if s > 0}

        if not positive:
            self._algo.log(
                f"SleeveA: no positive scores on {self._algo.time.date()} "
                f"→ parking {self._alloc:.0%} in {FALLBACK_ASSET}"
            )
            return {FALLBACK_ASSET: self._alloc}

        top_n = sorted(positive, key=positive.get, reverse=True)[:SECTOR_TOP_N]
        rp_w = risk_parity_weights(top_n, self._std, cap=MAX_POSITION)

        targets: dict[str, float] = {}
        for t, rw in rp_w.items():
            targets[t] = round(rw * self._alloc, 5)

        # Absorb any rounding residual (rare but possible when cap fires)
        allocated = sum(targets.values())
        leftover = round(self._alloc - allocated, 5)
        if leftover > 0.005:
            targets[FALLBACK_ASSET] = targets.get(FALLBACK_ASSET, 0.0) + leftover

        return targets

    def _score_sectors(self) -> dict[str, float]:
        """Composite score = (1-VALUE_BLEND)*momentum + VALUE_BLEND*value_rank."""
        scores: dict[str, float] = {}
        for t in SECTORS:
            mom = momentum_score(self._mom.get(t), self._std.get(t))
            if mom == -999.0:
                continue
            val = value_rank(t, SECTORS, self._long_mom)
            scores[t] = (1 - VALUE_BLEND) * mom + VALUE_BLEND * val
        return scores

    def describe(self) -> str:
        """Top-N sectors and their scores for logging."""
        scores = self._score_sectors()
        top = sorted(scores, key=scores.get, reverse=True)[: SECTOR_TOP_N + 2]
        parts = [f"{t}={scores[t]:.3f}" for t in top if t in scores]
        return "SleeveA scores: " + ", ".join(parts)
