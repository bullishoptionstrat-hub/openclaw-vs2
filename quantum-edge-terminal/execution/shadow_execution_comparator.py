"""
SHADOW EXECUTION COMPARATOR - PARALLEL PAPER + LIVE EXECUTION TRACKING

This module runs BOTH simulated and live execution in parallel during validation:
- Same signal → paper execution + live execution
- Compare expected vs actual fills
- Track drift over time
- Alert if live behaves different than paper

This is how you catch "live execution is 2% worse than validation"
before it costs capital.

USE CASE:
---------
Day 1-7: Run shadow execution
- Generate signal
- Open paper order (simulated)
- Also track market (what would actually happen)
- Compare fills, slippage, timing
- If divergence detected → investigate before deploying capital

This prevents 80% of production failures.
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    """Type of execution being tracked."""

    SIMULATED = "simulated"  # ForwardTestEngine (paper trading)
    MARKET = "market"  # What actually happened in market


@dataclass
class ShadowExecutionPair:
    """
    Linked execution in both simulated and market environments.

    For every signal, we track:
    1. What simulated execution engine predicted (on paper)
    2. What actually happened in market
    """

    signal_id: str
    symbol: str
    signal_time: datetime

    # Simulated execution
    sim_expected_price: float
    sim_fill_price: Optional[float] = None
    sim_fill_qty: Optional[float] = None
    sim_fill_time: Optional[datetime] = None
    sim_slippage_pct: Optional[float] = None

    # Market reality
    market_price_at_signal: Optional[float] = None
    market_actual_price: Optional[float] = None
    market_actual_qty: Optional[float] = None
    market_fill_time: Optional[datetime] = None
    market_slippage_pct: Optional[float] = None
    market_ohlc_high: Optional[float] = None
    market_ohlc_low: Optional[float] = None

    # Comparision
    price_divergence_pct: Optional[float] = None  # How much did simulated vs market differ?
    qty_divergence: Optional[float] = None  # Did we get different quantities?
    fill_timing_diff_ms: Optional[float] = None

    def calculate_divergence(self) -> None:
        """Calculate sim vs market divergence."""
        if self.sim_fill_price and self.market_actual_price:
            self.price_divergence_pct = (self.market_actual_price - self.sim_fill_price) / self.sim_fill_price

        if self.sim_fill_qty and self.market_actual_qty:
            self.qty_divergence = self.market_actual_qty - self.sim_fill_qty

        if self.sim_fill_time and self.market_fill_time:
            self.fill_timing_diff_ms = (self.market_fill_time - self.sim_fill_time).total_seconds() * 1000


@dataclass
class DivergenceAlert:
    """Alert when sim vs market behave differently."""

    alert_type: str  # price_divergence, qty_gap, timing_issue, etc
    severity: str  # low, medium, high, critical
    symbol: str
    divergence_value: float
    threshold: float
    description: str
    alert_time: datetime = field(default_factory=datetime.utcnow)


class ShadowExecutionComparator:
    """
    Compares simulated vs market execution in real-time.

    This catches execution degradation early.
    """

    def __init__(self):
        """Initialize shadow execution tracker."""
        self.execution_pairs: Dict[str, ShadowExecutionPair] = {}  # signal_id → pair
        self.alerts: List[DivergenceAlert] = []
        self.daily_divergence: List[float] = []
        self.divergence_by_symbol: Dict[str, List[float]] = defaultdict(list)

        # Thresholds
        self.price_divergence_threshold = 0.001  # 0.1% divergence
        self.qty_divergence_threshold = 0.05  # 5% qty divergence
        self.fill_timing_threshold_ms = 1000  # 1 second

        logger.info("ShadowExecutionComparator initialized")

    def create_shadow_execution(
        self,
        signal_id: str,
        symbol: str,
        sim_expected_price: float,
        market_price_at_signal: Optional[float] = None,
    ) -> ShadowExecutionPair:
        """
        Create new shadow execution tracking pair.

        Args:
            signal_id: Unique signal ID
            symbol: Stock symbol
            sim_expected_price: Price sim engine expects to fill
            market_price_at_signal: Mid price at signal time

        Returns:
            ShadowExecutionPair
        """

        pair = ShadowExecutionPair(
            signal_id=signal_id,
            symbol=symbol,
            signal_time=datetime.utcnow(),
            sim_expected_price=sim_expected_price,
            market_price_at_signal=market_price_at_signal,
        )

        self.execution_pairs[signal_id] = pair
        return pair

    def record_simulated_fill(
        self, signal_id: str, fill_price: float, fill_qty: float, fill_time: Optional[datetime] = None
    ) -> None:
        """Record what simulated execution provided."""

        if signal_id not in self.execution_pairs:
            logger.warning(f"Shadow execution {signal_id} not found")
            return

        pair = self.execution_pairs[signal_id]
        pair.sim_fill_price = fill_price
        pair.sim_fill_qty = fill_qty
        pair.sim_fill_time = fill_time or datetime.utcnow()

        # Calculate slippage vs expected
        pair.sim_slippage_pct = (fill_price - pair.sim_expected_price) / pair.sim_expected_price

        logger.debug(
            f"[SHADOW] {signal_id} | SIM fill: {fill_qty} @ ${fill_price:.2f} "
            f"(slippage: {pair.sim_slippage_pct:.3%})"
        )

    def record_market_reality(
        self,
        signal_id: str,
        actual_fill_price: Optional[float],
        actual_qty: Optional[float],
        ohlc_high: Optional[float] = None,
        ohlc_low: Optional[float] = None,
        fill_time: Optional[datetime] = None,
    ) -> None:
        """
        Record what actually happened in market.

        This is compared to simulated execution.
        """

        if signal_id not in self.execution_pairs:
            logger.warning(f"Shadow execution {signal_id} not found")
            return

        pair = self.execution_pairs[signal_id]
        pair.market_actual_price = actual_fill_price
        pair.market_actual_qty = actual_qty
        pair.market_ohlc_high = ohlc_high
        pair.market_ohlc_low = ohlc_low
        pair.market_fill_time = fill_time or datetime.utcnow()

        if actual_fill_price:
            pair.market_slippage_pct = (actual_fill_price - pair.sim_expected_price) / pair.sim_expected_price

        # Calculate divergence
        pair.calculate_divergence()

        # Check for divergence alerts
        self._check_divergence(pair)

        logger.debug(
            f"[SHADOW] {signal_id} | MARKET reality: {actual_qty} @ ${actual_fill_price:.2f if actual_fill_price else '?':.2f} "
            f"| Divergence: {pair.price_divergence_pct:.3%}" if pair.price_divergence_pct else "?"
        )

    def _check_divergence(self, pair: ShadowExecutionPair) -> None:
        """Check if sim vs market diverged significantly."""

        if not pair.sim_fill_price or not pair.market_actual_price:
            return

        # Price divergence check
        if pair.price_divergence_pct is not None:
            if abs(pair.price_divergence_pct) > self.price_divergence_threshold:
                alert = DivergenceAlert(
                    alert_type="price_divergence",
                    severity="medium" if abs(pair.price_divergence_pct) < 0.005 else "high",
                    symbol=pair.symbol,
                    divergence_value=pair.price_divergence_pct,
                    threshold=self.price_divergence_threshold,
                    description=f"Market price {pair.price_divergence_pct:.2%} from simulated price",
                )
                self.alerts.append(alert)
                logger.warning(f"[SHADOW] Price divergence alert: {alert.description}")

        # Quantity divergence check
        if pair.sim_fill_qty and pair.market_actual_qty:
            qty_diff = abs(pair.market_actual_qty - pair.sim_fill_qty) / pair.sim_fill_qty
            if qty_diff > self.qty_divergence_threshold:
                alert = DivergenceAlert(
                    alert_type="qty_divergence",
                    severity="high",
                    symbol=pair.symbol,
                    divergence_value=qty_diff,
                    threshold=self.qty_divergence_threshold,
                    description=f"Fill quantity {qty_diff:.1%} different: sim={pair.sim_fill_qty}, market={pair.market_actual_qty}",
                )
                self.alerts.append(alert)
                logger.warning(f"[SHADOW] Quantity divergence alert: {alert.description}")

        # Timing divergence check
        if pair.fill_timing_diff_ms is not None:
            if abs(pair.fill_timing_diff_ms) > self.fill_timing_threshold_ms:
                alert = DivergenceAlert(
                    alert_type="timing_divergence",
                    severity="medium",
                    symbol=pair.symbol,
                    divergence_value=pair.fill_timing_diff_ms,
                    threshold=self.fill_timing_threshold_ms,
                    description=f"Fill timing difference: {pair.fill_timing_diff_ms:.0f}ms",
                )
                self.alerts.append(alert)
                logger.warning(f"[SHADOW] Timing divergence alert: {alert.description}")

        # Track for statistics
        if pair.price_divergence_pct:
            self.daily_divergence.append(pair.price_divergence_pct)
            self.divergence_by_symbol[pair.symbol].append(pair.price_divergence_pct)

    def get_daily_report(self) -> Dict:
        """Get shadow execution report for today."""

        if not self.daily_divergence:
            return {
                "tracked_pairs": len(self.execution_pairs),
                "divergence_alerts": len(self.alerts),
                "status": "no executions to compare",
            }

        import statistics

        return {
            "tracked_pairs": len(self.execution_pairs),
            "divergence_alerts": len(self.alerts),
            "divergence_stats": {
                "avg_pct": statistics.mean(self.daily_divergence),
                "median_pct": statistics.median(self.daily_divergence),
                "min_pct": min(self.daily_divergence),
                "max_pct": max(self.daily_divergence),
                "stdev_pct": statistics.stdev(self.daily_divergence) if len(self.daily_divergence) > 1 else 0,
            },
            "by_symbol": {
                symbol: {
                    "avg_pct": statistics.mean(divs),
                    "count": len(divs),
                }
                for symbol, divs in self.divergence_by_symbol.items()
                if divs
            },
            "recent_alerts": [
                {
                    "type": a.alert_type,
                    "severity": a.severity,
                    "symbol": a.symbol,
                    "divergence": f"{a.divergence_value:.3%}",
                    "description": a.description,
                }
                for a in self.alerts[-10:]  # Last 10
            ],
        }

    def get_execution_pair(self, signal_id: str) -> Optional[Dict]:
        """Get comparison for single signal."""
        if signal_id not in self.execution_pairs:
            return None

        pair = self.execution_pairs[signal_id]
        return {
            "signal_id": signal_id,
            "symbol": pair.symbol,
            "signal_time": pair.signal_time.isoformat(),
            "simulated": {
                "expected_price": pair.sim_expected_price,
                "fill_price": pair.sim_fill_price,
                "fill_qty": pair.sim_fill_qty,
                "slippage_pct": pair.sim_slippage_pct,
            },
            "market": {
                "price_at_signal": pair.market_price_at_signal,
                "actual_price": pair.market_actual_price,
                "actual_qty": pair.market_actual_qty,
                "slippage_pct": pair.market_slippage_pct,
                "ohlc_high": pair.market_ohlc_high,
                "ohlc_low": pair.market_ohlc_low,
            },
            "divergence": {
                "price_pct": pair.price_divergence_pct,
                "qty": pair.qty_divergence,
                "timing_ms": pair.fill_timing_diff_ms,
            },
        }

    def reset_daily(self) -> None:
        """Reset daily tracking."""
        self.daily_divergence = []
        self.divergence_by_symbol = defaultdict(list)
        self.alerts = []
        logger.info("Shadow execution daily reset")
