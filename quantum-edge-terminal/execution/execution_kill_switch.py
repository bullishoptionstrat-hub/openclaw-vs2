"""
EXECUTION KILL SWITCH - AUTOMATIC CIRCUIT BREAKER FOR EXECUTION FAILURES

This module monitors execution quality in real-time and STOPS trading when:
- API error rate exceeds threshold
- Slippage spikes abnormally
- Fill rate drops below acceptable level
- Signals are sent but never filled (missed trades)
- Order submission timeout
- Systematic execution degradation detected

This is the last line of defense before capital loss.

TRIGGERS (ANY FIRES → TRADING HALTED):
1. API Error Rate > 5% in last hour
2. Slippage > 0.15% for 5+ consecutive trades
3. Fill Rate < 80% for 10+ submitted orders
4. Missed Trades > 3 in last 100 signals
5. Submit-to-Ack timeout > 5000ms consistently
6. Order Ack-to-Fill > 1 minute (system gone)
"""

import logging
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta

from execution_audit_log import ExecutionAuditLog, FillQuality

logger = logging.getLogger(__name__)


class KillSwitchTrigger(Enum):
    """Reasons trading was halted."""

    API_ERROR_RATE = "api_error_rate_exceeded"
    SLIPPAGE_SPIKE = "slippage_spike"
    FILL_RATE_DROP = "fill_rate_below_threshold"
    MISSED_TRADES = "missed_trades_exceeded"
    SUBMISSION_TIMEOUT = "order_submission_timeout"
    FILL_TIMEOUT = "fill_ack_timeout"
    EXECUTION_DEGRADATION = "execution_degradation_detected"
    MANUAL_STOP = "manual_stop"


@dataclass
class KillSwitchThresholds:
    """Configurable circuit breaker thresholds."""

    # API health
    max_api_error_rate: float = 0.05  # 5% API errors
    api_error_window_minutes: int = 60

    # Slippage
    max_consecutive_bad_fills: int = 5  # 5+ trades with bad slippage
    slippage_degradation_threshold: float = 0.0015  # 0.15% bad slippage

    # Fill rate
    min_fill_rate: float = 0.80  # 80% minimum fill rate
    fill_rate_window_trades: int = 10  # Look at last 10 orders

    # Missed trades
    max_missed_trades_pct: float = 0.03  # 3% of signals can be missed
    missed_trades_window_trades: int = 100

    # Timing
    max_submit_to_ack_ms: float = 5000.0  # 5 second timeout to ack
    max_ack_to_fill_ms: float = 60000.0  # 1 minute timeout to fill


@dataclass
class KillSwitchStatus:
    """Current kill switch status."""

    is_active: bool  # True = trading halted
    triggered_by: Optional[KillSwitchTrigger] = None
    trigger_time: Optional[datetime] = None
    trigger_details: Dict = None
    halt_reason: Optional[str] = None

    def to_dict(self) -> Dict:
        """Serialize to dict."""
        return {
            "is_active": self.is_active,
            "triggered_by": self.triggered_by.value if self.triggered_by else None,
            "trigger_time": self.trigger_time.isoformat() if self.trigger_time else None,
            "halt_reason": self.halt_reason,
            "trigger_details": self.trigger_details,
        }


class ExecutionKillSwitch:
    """
    Monitors execution quality and halts trading on failures.

    This is NOT optional. Every production trade goes through this check.
    """

    def __init__(self, audit_log: ExecutionAuditLog, thresholds: KillSwitchThresholds = None):
        """
        Initialize kill switch.

        Args:
            audit_log: ExecutionAuditLog to monitor
            thresholds: KillSwitchThresholds config (or default)
        """
        self.audit_log = audit_log
        self.thresholds = thresholds or KillSwitchThresholds()
        self.status = KillSwitchStatus(is_active=False)

        logger.info("ExecutionKillSwitch initialized")
        logger.info(f"  Max API error rate: {self.thresholds.max_api_error_rate:.1%}")
        logger.info(f"  Max slippage threshold: {self.thresholds.slippage_degradation_threshold:.3%}")
        logger.info(f"  Min fill rate: {self.thresholds.min_fill_rate:.0%}")
        logger.info(f"  Max missed trades: {self.thresholds.max_missed_trades_pct:.1%}")

    def check_execution_health(self) -> bool:
        """
        Check if execution environment is healthy.

        Returns:
            True if healthy (trading OK), False if halted
        """

        if self.status.is_active:
            # Already halted
            return False

        # Run all checks
        checks = [
            self._check_api_error_rate(),
            self._check_slippage_spike(),
            self._check_fill_rate(),
            self._check_missed_trades(),
            self._check_submission_timeout(),
            self._check_fill_timeout(),
        ]

        if any(not check for check in checks):
            # One or more failed - already logged and status updated
            return False

        return True

    def _check_api_error_rate(self) -> bool:
        """Check API error rate isn't too high."""
        stats = self.audit_log.get_execution_stats(window_minutes=self.thresholds.api_error_window_minutes)

        if stats["total_executions"] < 5:
            # Not enough data
            return True

        if stats["total_executions"] == 0:
            return True

        error_rate = stats["rejected"] / stats["total_executions"]

        if error_rate > self.thresholds.max_api_error_rate:
            self._trigger(
                KillSwitchTrigger.API_ERROR_RATE,
                f"API error rate {error_rate:.1%} exceeds threshold {self.thresholds.max_api_error_rate:.1%}",
                {
                    "rejected": stats["rejected"],
                    "total": stats["total_executions"],
                    "error_rate": error_rate,
                },
            )
            return False

        return True

    def _check_slippage_spike(self) -> bool:
        """Check for abnormal slippage spikes."""
        stats = self.audit_log.get_execution_stats(window_minutes=30)  # Last 30 min

        if stats["total_executions"] < self.thresholds.max_consecutive_bad_fills + 2:
            # Not enough data
            return True

        # Get recent records
        recent_records = list(self.audit_log.records.values())[-20:]  # Last 20
        recent_records = [r for r in recent_records if r.prices and r.prices.slippage_pct is not None]

        if not recent_records:
            return True

        # Check for consecutive bad fills
        bad_count = 0
        for record in recent_records:
            if record.get_fill_quality() in [FillQuality.POOR, FillQuality.BAD]:
                bad_count += 1
            else:
                bad_count = 0

            if bad_count >= self.thresholds.max_consecutive_bad_fills:
                avg_slippage = sum(
                    r.prices.slippage_pct for r in recent_records[-bad_count:] if r.prices
                ) / bad_count
                self._trigger(
                    KillSwitchTrigger.SLIPPAGE_SPIKE,
                    f"{bad_count} consecutive trades with poor slippage (avg {avg_slippage:.3%})",
                    {
                        "consecutive_bad_fills": bad_count,
                        "avg_slippage_pct": avg_slippage,
                        "threshold": self.thresholds.slippage_degradation_threshold,
                    },
                )
                return False

        return True

    def _check_fill_rate(self) -> bool:
        """Check fill rate is acceptable."""
        recent_records = list(self.audit_log.records.values())[-self.thresholds.fill_rate_window_trades :]

        if len(recent_records) < 5:
            # Not enough data
            return True

        filled = len([r for r in recent_records if r.is_complete and r.status != "rejected"])
        total = len([r for r in recent_records if r.status != "rejected"])

        if total == 0:
            return True

        fill_rate = filled / total

        if fill_rate < self.thresholds.min_fill_rate:
            self._trigger(
                KillSwitchTrigger.FILL_RATE_DROP,
                f"Fill rate {fill_rate:.0%} below threshold {self.thresholds.min_fill_rate:.0%}",
                {
                    "filled": filled,
                    "total": total,
                    "fill_rate": fill_rate,
                },
            )
            return False

        return True

    def _check_missed_trades(self) -> bool:
        """Check for missed trades (signal sent, no fill)."""
        recent_records = list(self.audit_log.records.values())[-self.thresholds.missed_trades_window_trades :]

        if len(recent_records) < 10:
            return True

        missed = len([r for r in recent_records if r.status == "rejected" or (r.status == "pending" and r.order_submit_time)])
        total = len(recent_records)

        missed_pct = missed / total if total > 0 else 0

        if missed_pct > self.thresholds.max_missed_trades_pct:
            self._trigger(
                KillSwitchTrigger.MISSED_TRADES,
                f"Missed {missed_pct:.1%} of trades (threshold: {self.thresholds.max_missed_trades_pct:.1%})",
                {
                    "missed": missed,
                    "total": total,
                    "missed_pct": missed_pct,
                },
            )
            return False

        return True

    def _check_submission_timeout(self) -> bool:
        """Check order submission isn't timing out."""
        recent_records = list(self.audit_log.records.values())[-50:]
        records_with_timing = [r for r in recent_records if r.total_delay_ms is not None]

        if len(records_with_timing) < 5:
            return True

        # Look for consistent delays > threshold
        slow_orders = [r for r in records_with_timing if r.total_delay_ms > self.thresholds.max_submit_to_ack_ms]

        if len(slow_orders) >= 3:
            avg_delay = sum(r.total_delay_ms for r in records_with_timing) / len(records_with_timing)
            self._trigger(
                KillSwitchTrigger.SUBMISSION_TIMEOUT,
                f"Order submission consistently slow: {avg_delay:.0f}ms (max: {self.thresholds.max_submit_to_ack_ms:.0f}ms)",
                {
                    "slow_orders": len(slow_orders),
                    "avg_delay_ms": avg_delay,
                    "max_allowed_ms": self.thresholds.max_submit_to_ack_ms,
                },
            )
            return False

        return True

    def _check_fill_timeout(self) -> bool:
        """Check fills aren't timing out (ack → fill > 1 min)."""
        recent_records = list(self.audit_log.records.values())[-50:]
        records_with_fill_time = [r for r in recent_records if r.ack_to_first_fill_ms is not None]

        if len(records_with_fill_time) < 5:
            return True

        # Check for fills taking > max time
        slow_fills = [r for r in records_with_fill_time if r.ack_to_first_fill_ms > self.thresholds.max_ack_to_fill_ms]

        if len(slow_fills) >= 2:
            avg_fill_time = sum(r.ack_to_first_fill_ms for r in records_with_fill_time) / len(records_with_fill_time)
            self._trigger(
                KillSwitchTrigger.FILL_TIMEOUT,
                f"Fills timing out: {avg_fill_time:.0f}ms avg (max: {self.thresholds.max_ack_to_fill_ms:.0f}ms)",
                {
                    "slow_fills": len(slow_fills),
                    "avg_fill_time_ms": avg_fill_time,
                    "max_allowed_ms": self.thresholds.max_ack_to_fill_ms,
                },
            )
            return False

        return True

    def _trigger(self, trigger_type: KillSwitchTrigger, reason: str, details: Dict = None) -> None:
        """Trigger kill switch."""
        self.status.is_active = True
        self.status.triggered_by = trigger_type
        self.status.trigger_time = datetime.utcnow()
        self.status.halt_reason = reason
        self.status.trigger_details = details or {}

        logger.critical("🛑 " + "=" * 80)
        logger.critical(f"🛑 EXECUTION KILL SWITCH TRIGGERED")
        logger.critical(f"🛑 Reason: {trigger_type.value}")
        logger.critical(f"🛑 Details: {reason}")
        logger.critical(f"🛑 " + "=" * 80)

    def manual_stop(self, reason: str) -> None:
        """Manually stop trading."""
        self._trigger(KillSwitchTrigger.MANUAL_STOP, reason)

    def reset(self) -> None:
        """Reset kill switch (after investigation)."""
        prev_trigger = self.status.triggered_by
        self.status = KillSwitchStatus(is_active=False)
        logger.warning(f"⚙️  Kill switch reset (was: {prev_trigger.value if prev_trigger else 'none'})")

    def get_status(self) -> Dict:
        """Get current status."""
        return self.status.to_dict()
