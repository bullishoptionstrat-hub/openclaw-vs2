"""
Regime filter — determines equity vs defensive mode.

Inputs:  Lean indicator objects (already wired in initialize())
Outputs: bool (True = equity mode)

Design contract:
  - Must be stateless between calls (reads indicator state only)
  - Must degrade gracefully if VXX data is missing
  - Must log every regime flip explicitly
"""

from AlgorithmImports import *
from algorithm.config import (
    USE_SPY_SMA_FILTER,
    USE_VXX_FILTER,
)


class RegimeFilter:
    """
    Dual-condition equity regime:
      (1) SPY > TREND_SMA_DAYS-day SMA   [primary, always used if enabled]
      (2) VXX < VXX_SMA_DAYS-day SMA    [secondary, skipped if VXX not ready]

    If USE_REGIME_FILTER is False, always returns True (equity).
    If USE_SPY_SMA_FILTER is False, condition (1) is always satisfied.
    If USE_VXX_FILTER is False, condition (2) is skipped.
    """

    def __init__(
        self,
        algorithm: QCAlgorithm,
        spy_sma: SimpleMovingAverage,
        vxx_sma: SimpleMovingAverage,
        spy_sym: Symbol,
        vxx_sym: Symbol,
        use_regime_filter: bool,
    ):
        self._algo = algorithm
        self._spy_sma = spy_sma
        self._vxx_sma = vxx_sma
        self._spy_sym = spy_sym
        self._vxx_sym = vxx_sym
        self._use_regime = use_regime_filter
        self._last_regime: bool | None = None

    # ------------------------------------------------------------------

    def is_equity(self) -> bool:
        if not self._use_regime:
            return True

        result = self._spy_condition() and self._vxx_condition()

        # Log flips
        if self._last_regime is not None and result != self._last_regime:
            label = "EQUITY" if result else "DEFENSIVE"
            self._algo.log(f"REGIME FLIP → {label}  [{self._algo.time.date()}]")
        self._last_regime = result
        return result

    def _spy_condition(self) -> bool:
        if not USE_SPY_SMA_FILTER:
            return True
        if not self._spy_sma.is_ready:
            return True  # default equity during warmup
        spy_price = self._algo.securities[self._spy_sym].price
        if spy_price == 0:
            return True
        return bool(spy_price > self._spy_sma.current.value)

    def _vxx_condition(self) -> bool:
        if not USE_VXX_FILTER:
            return True
        if not self._vxx_sma.is_ready:
            # VXX data unavailable (before Jan 2018 in local setup) — skip
            return True
        vxx_price = self._algo.securities[self._vxx_sym].price
        if vxx_price == 0:
            return True
        return bool(vxx_price <= self._vxx_sma.current.value)

    def describe(self) -> str:
        """Human-readable state for logging."""
        spy_ok = self._spy_condition()
        vxx_ok = self._vxx_condition()
        vxx_rdy = self._vxx_sma.is_ready
        return (
            f"SPY_above_SMA={spy_ok}  "
            f"VXX_calm={vxx_ok if vxx_rdy else 'N/A(not_ready)'}  "
            f"→ {'EQUITY' if (spy_ok and vxx_ok) else 'DEFENSIVE'}"
        )
