"""
Sleeve B — Greenblatt Magic Formula

STATUS: DISABLED BY DEFAULT — LOCAL DATA UNAVAILABLE
======================================================

This sleeve requires QuantConnect coarse/fine fundamental data:
  - dollar_volume (coarse)
  - ev_to_ebitda  (fine / valuation_ratios)
  - forward_roa   (fine / valuation_ratios, used as ROC proxy)
  - pe_ratio, basic_average_shares, basic_eps (fine, for market cap filter)

None of this data is present in the local Lean install.
Enabling ENABLE_SLEEVE_B without this data causes:
  - 100% failed universe requests
  - Zero stocks ever selected
  - Entire Sleeve B allocation silently sitting in SHY
  - Artificially depressed CAGR (~40% of portfolio yielding 0%)

VALIDATION STATE
----------------
- local_data_valid: False  (no fundamental data)
- cloud_data_valid: untested
- backtest_verified: False

WHEN TO ENABLE
--------------
Enable only after verifying:
  1. lean/Data/equity/usa/fundamental/ contains coarse + fine data files
  2. A test run shows > 0 stocks selected in select_fine()
  3. universe requests show < 10% failure rate in DataMonitor output

FALLBACK BEHAVIOUR
------------------
When disabled (ENABLE_SLEEVE_B = False), the Allocator redistributes
Sleeve B's weight proportionally to the active sleeves (A + C).
This is intentional and logged.
"""

from __future__ import annotations
from AlgorithmImports import *
from algorithm.config import (
    GREENBLATT_N_PORTFOLIO,
    MAX_POSITION,
    FALLBACK_ASSET,
)
from strategy.signals import risk_parity_weights


class SleeveB:
    """
    Greenblatt Magic Formula stock sleeve.

    In a valid run this selects 10 stocks ranked by EV/EBITDA + ROC
    from the QC500 universe, sized by risk-parity.

    In the current local setup this will always return an empty symbol set
    and fall back to FALLBACK_ASSET.  The validate() method makes this explicit.
    """

    # Data availability tag — set to True only when verified
    DATA_AVAILABLE: bool = False

    def __init__(
        self,
        algorithm: QCAlgorithm,
        std_map: dict[Symbol, StandardDeviation],
        allocation: float,
    ):
        self._algo = algorithm
        self._std = std_map
        self._alloc = allocation
        self._validated = False

    # ------------------------------------------------------------------

    def validate(self) -> bool:
        """
        Check whether Sleeve B can actually run.

        Returns True only if fundamental data is confirmed present.
        Always call this in initialize() if ENABLE_SLEEVE_B is True.
        """
        if not self.DATA_AVAILABLE:
            self._algo.log(
                "=" * 60 + "\n"
                "SLEEVE B WARNING: DATA_AVAILABLE = False\n"
                "  Fundamental data (coarse/fine) NOT found locally.\n"
                "  Sleeve B cannot select stocks.\n"
                "  Entire allocation will park in SHY.\n"
                "  This result is NOT a valid Greenblatt backtest.\n"
                "  Set DATA_AVAILABLE = True only after verifying data.\n" + "=" * 60
            )
            self._validated = False
            return False
        self._validated = True
        return True

    # ------------------------------------------------------------------

    def targets(
        self,
        equity_regime: bool,
        active_symbols: set[Symbol],
    ) -> dict:
        """
        Return Symbol → portfolio weight for Sleeve B.

        If regime is defensive, data unavailable, or no stocks selected:
        returns {FALLBACK_ASSET: allocation} with a logged explanation.
        """
        if not equity_regime:
            return {FALLBACK_ASSET: self._alloc}

        if not self._validated or not self.DATA_AVAILABLE:
            return {FALLBACK_ASSET: self._alloc}

        # Filter to stocks with live prices and ready vol indicators
        tradeable = [
            s
            for s in active_symbols
            if self._algo.securities.get(s) is not None and self._algo.securities[s].price > 0
        ]
        if not tradeable:
            self._algo.log(
                f"SleeveB: 0 tradeable stocks on {self._algo.time.date()} "
                f"→ parking {self._alloc:.0%} in {FALLBACK_ASSET}"
            )
            return {FALLBACK_ASSET: self._alloc}

        # Equal weight (risk-parity falls back to equal when vol not ready)
        ready_std = {s: v for s, v in self._std.items() if v.is_ready}
        tradeable_std = {s: ready_std[s] for s in tradeable if s in ready_std}

        if tradeable_std:
            rp = risk_parity_weights(
                list(tradeable_std.keys()),
                tradeable_std,
                cap=MAX_POSITION,
            )
        else:
            # Fallback to equal weight
            n = len(tradeable)
            rp = {s: 1.0 / n for s in tradeable}

        targets: dict = {}
        for s, rw in rp.items():
            targets[s] = round(rw * self._alloc, 5)

        allocated = sum(targets.values())
        leftover = round(self._alloc - allocated, 5)
        if leftover > 0.005:
            targets[FALLBACK_ASSET] = leftover

        return targets

    def describe(self) -> str:
        if not self.DATA_AVAILABLE:
            return "SleeveB: DISABLED (no local fundamental data)"
        return f"SleeveB: DATA_AVAILABLE=True, allocation={self._alloc:.0%}"
