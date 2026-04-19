"""
Sleeve C — IBS Mean Reversion

Alpha source: Internal Bar Strength (IBS) on 12 global equity ETFs.
Strategy: long the N most oversold (IBS near 0), short the N most overbought.
Sizing: risk-parity within each leg.

IBS = (Close - Low) / (High - Low), range [0, 1]
Lower IBS → oversold → buy
Higher IBS → overbought → sell short

This sleeve is always active regardless of regime (provides diversification
and negative beta exposure in sell-offs via short leg).
"""

from __future__ import annotations
from AlgorithmImports import *
from algorithm.config import (
    IBS_ETFS,
    IBS_TOP_N,
    MAX_POSITION,
    FALLBACK_ASSET,
)
from strategy.signals import ibs_score, risk_parity_weights


class SleeveC:
    """
    IBS mean-reversion sleeve.

    Args:
        algorithm: parent QCAlgorithm (logging only)
        sym_map:   ticker → Symbol
        std_map:   ticker → StandardDeviation
        allocation: fraction of total portfolio (effective, already scaled)
    """

    def __init__(
        self,
        algorithm: QCAlgorithm,
        sym_map: dict[str, Symbol],
        std_map: dict[str, StandardDeviation],
        allocation: float,
    ):
        self._algo = algorithm
        self._sym = sym_map
        self._std = std_map
        self._alloc = allocation

    # ------------------------------------------------------------------

    def targets(self) -> dict[str, float]:
        """
        Return ticker → portfolio weight for Sleeve C.

        Long leg:  +allocation/2 split among top-N oversold
        Short leg: -allocation/2 split among top-N overbought
        Fallback to FALLBACK_ASSET if fewer than 2*IBS_TOP_N ETFs available.
        """
        available = {
            t: ibs_score(self._algo.securities.get(self._sym.get(t)))
            for t in IBS_ETFS
            if self._sym.get(t) is not None
            and self._algo.securities.get(self._sym[t]) is not None
            and self._algo.securities[self._sym[t]].price > 0
        }

        min_required = 2 * IBS_TOP_N
        if len(available) < min_required:
            self._algo.log(
                f"SleeveC: only {len(available)} ETFs available "
                f"(need {min_required}) → parking {self._alloc:.0%} "
                f"in {FALLBACK_ASSET}"
            )
            return {FALLBACK_ASSET: self._alloc}

        ranked = sorted(available.items(), key=lambda x: x[1])
        to_long = [t for t, _ in ranked[:IBS_TOP_N]]
        to_short = [t for t, _ in ranked[-IBS_TOP_N:]]

        long_w = risk_parity_weights(to_long, self._std, cap=MAX_POSITION)
        short_w = risk_parity_weights(to_short, self._std, cap=MAX_POSITION)

        half = self._alloc / 2.0
        targets: dict[str, float] = {}

        for t, rw in long_w.items():
            targets[t] = round(rw * half, 5)

        for t, rw in short_w.items():
            # Accumulate: ticker could appear in both legs (unlikely but safe)
            targets[t] = targets.get(t, 0.0) - round(rw * half, 5)

        return targets

    def describe(self) -> str:
        available = {
            t: ibs_score(self._algo.securities.get(self._sym.get(t)))
            for t in IBS_ETFS
            if self._sym.get(t) is not None
            and self._algo.securities.get(self._sym[t]) is not None
            and self._algo.securities[self._sym[t]].price > 0
        }
        ranked = sorted(available.items(), key=lambda x: x[1])
        oversold = [f"{t}={v:.2f}" for t, v in ranked[:IBS_TOP_N]]
        overbought = [f"{t}={v:.2f}" for t, v in ranked[-IBS_TOP_N:]]
        return f"SleeveC IBS  long={oversold}  short={overbought}"
