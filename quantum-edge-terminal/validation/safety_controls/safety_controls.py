"""
SAFETY CONTROLS - INSTITUTIONAL KILL SWITCHES

This layer prevents blowups and catastrophic failures.

Implements:
- Daily loss limit (hard stop)
- Max consecutive losses
- Stale data detection
- API disconnect handling
- Duplicate signal prevention
- Circuit breaker (auto-disable after failures)

Philosophy: Default to SAFE MODE unless explicitly approved
"""

import logging
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class SafetyStatus(Enum):
    """Safety system status."""

    ACTIVE = "ACTIVE"  # System operating normally
    WARNING = "WARNING"  # Alert conditions met
    LOCKDOWN = "LOCKDOWN"  # System disabled (circuit breaker)


@dataclass
class SafetyEvent:
    """Record of a safety event."""

    timestamp: datetime
    event_type: str  # "daily_loss", "consecutive_losses", "stale_data", etc
    severity: str  # "warning", "critical"
    message: str


class SafetyControls:
    """
    Institutional-grade safety system.

    Prevents:
    - Runaway losses
    - Stale data trading
    - Duplicate orders
    - API failures
    - Cascade failures
    """

    def __init__(
        self,
        max_daily_loss_pct: float = 0.05,
        max_consecutive_losses: int = 5,
        max_open_trades: int = 5,
        stale_data_threshold_seconds: int = 60,
    ):
        """
        Initialize safety controls.

        Args:
            max_daily_loss_pct: Daily loss limit as % of capital (default 5%)
            max_consecutive_losses: Max consecutive losing trades before lockdown
            max_open_trades: Max concurrent positions
            stale_data_threshold_seconds: Max age for market data before stale
        """

        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_consecutive_losses = max_consecutive_losses
        self.max_open_trades = max_open_trades
        self.stale_data_threshold = timedelta(seconds=stale_data_threshold_seconds)

        # State
        self.daily_pnl = 0.0
        self.daily_loss_count = 0
        self.consecutive_losses = 0
        self.safety_status = SafetyStatus.ACTIVE
        self.circuit_breaker_active = False
        self.safety_events: List[SafetyEvent] = []

        # Tracking
        self.last_market_data_timestamp: datetime = None
        self.last_successful_trade_timestamp: datetime = None
        self.recent_signal_ids: List[str] = []
        self.api_error_count = 0
        self.consecutive_api_errors = 0

        # Session reset time
        self.session_reset_time = datetime.now()

        logger.info(
            f"SafetyControls initialized | "
            f"Daily loss limit: {max_daily_loss_pct * 100:.1f}% | "
            f"Max consecutive losses: {max_consecutive_losses}"
        )

    def check_market_data_freshness(
        self, data_timestamp: datetime
    ) -> Tuple[bool, str]:
        """
        Check if market data is fresh (not stale).

        Args:
            data_timestamp: Timestamp of market data

        Returns:
            (is_fresh, reason)
        """

        now = datetime.now()
        age = now - data_timestamp

        if age > self.stale_data_threshold:
            reason = f"Stale data: {age.total_seconds():.1f}s old"
            logger.warning(f"🚨 {reason}")
            self._record_event(
                event_type="stale_data",
                severity="critical",
                message=reason,
            )
            return False, reason

        self.last_market_data_timestamp = now
        return True, "Data is fresh"

    def check_daily_loss_limit(self, account_equity: float) -> Tuple[bool, str]:
        """
        Check if daily loss exceeds maximum allowed.

        Args:
            account_equity: Current portfolio value

        Returns:
            (allows_trading, reason)
        """

        # Reset daily limits if new day
        self._check_daily_reset()

        if self.daily_pnl < 0:
            loss_pct = abs(self.daily_pnl) / account_equity

            if loss_pct > self.max_daily_loss_pct:
                reason = (
                    f"Daily loss limit exceeded: "
                    f"${abs(self.daily_pnl):.2f} ({loss_pct * 100:.1f}%) "
                    f"> limit ({self.max_daily_loss_pct * 100:.1f}%)"
                )
                logger.critical(f"🚨 {reason}")
                self._record_event(
                    event_type="daily_loss_exceeded",
                    severity="critical",
                    message=reason,
                )
                self.safety_status = SafetyStatus.LOCKDOWN
                return False, reason

        return True, f"Daily P&L OK: ${self.daily_pnl:.2f}"

    def check_consecutive_losses(self) -> Tuple[bool, str]:
        """
        Check if consecutive losses exceed threshold.

        Returns:
            (allows_trading, reason)
        """

        if self.consecutive_losses >= self.max_consecutive_losses:
            reason = (
                f"Consecutive losses limit: "
                f"{self.consecutive_losses}/{self.max_consecutive_losses}"
            )
            logger.warning(f"⚠️  {reason}")
            self._record_event(
                event_type="excessive_consecutive_losses",
                severity="warning",
                message=reason,
            )
            self.safety_status = SafetyStatus.WARNING
            return False, reason

        return True, f"Consecutive losses: {self.consecutive_losses}"

    def check_duplicate_signal(self, signal_id: str) -> Tuple[bool, str]:
        """
        Check if signal is duplicate of recent signal.

        Args:
            signal_id: Signal identifier

        Returns:
            (is_unique, reason)
        """

        if signal_id in self.recent_signal_ids:
            reason = f"Duplicate signal: {signal_id}"
            logger.warning(f"⚠️  {reason}")
            self._record_event(
                event_type="duplicate_signal",
                severity="warning",
                message=reason,
            )
            return False, reason

        # Add to recent (keep last 100)
        self.recent_signal_ids.append(signal_id)
        if len(self.recent_signal_ids) > 100:
            self.recent_signal_ids.pop(0)

        return True, "Signal is unique"

    def check_max_open_trades(self, open_trade_count: int) -> Tuple[bool, str]:
        """
        Check if open trade count exceeds maximum.

        Args:
            open_trade_count: Number of current open trades

        Returns:
            (allows_more_trades, reason)
        """

        if open_trade_count >= self.max_open_trades:
            reason = (
                f"Max open trades reached: "
                f"{open_trade_count}/{self.max_open_trades}"
            )
            logger.warning(f"⚠️  {reason}")
            return False, reason

        return True, f"Open trades: {open_trade_count}/{self.max_open_trades}"

    def record_trade_result(
        self, pnl: float, draw_profit: bool = False
    ) -> None:
        """
        Record result of a closed trade.

        Args:
            pnl: Profit/loss amount
            draw_profit: If True, don't increment consecutive losses on draw
        """

        self.daily_pnl += pnl
        self.last_successful_trade_timestamp = datetime.now()

        if pnl < 0:
            self.consecutive_losses += 1
            self.daily_loss_count += 1
            logger.warning(
                f"Loss recorded | P&L: ${pnl:.2f} | "
                f"Consecutive: {self.consecutive_losses}"
            )
        elif pnl > 0:
            self.consecutive_losses = 0  # Reset on win
            logger.info(f"Win recorded | P&L: ${pnl:.2f}")
        else:
            if not draw_profit:
                self.consecutive_losses += 1

    def record_api_error(self) -> None:
        """Record an API error."""
        self.api_error_count += 1
        self.consecutive_api_errors += 1

        logger.error(
            f"API error recorded | "
            f"Total: {self.api_error_count} | "
            f"Consecutive: {self.consecutive_api_errors}"
        )

        # Circuit breaker: 3+ consecutive API errors
        if self.consecutive_api_errors >= 3:
            self._activate_circuit_breaker(
                reason="Too many consecutive API errors"
            )

    def record_api_success(self) -> None:
        """Record successful API call."""
        self.consecutive_api_errors = 0

    def pre_trade_checks(
        self,
        signal_id: str,
        market_data_timestamp: datetime,
        account_equity: float,
        open_trade_count: int,
    ) -> Tuple[bool, List[str]]:
        """
        Run all pre-trade safety checks.

        Args:
            signal_id: Signal identifier
            market_data_timestamp: Timestamp of market data
            account_equity: Current account equity
            open_trade_count: Number of open trades

        Returns:
            (passes_all_checks, list_of_failures)
        """

        failures = []

        # Check circuit breaker first
        if self.circuit_breaker_active:
            failures.append("Circuit breaker active - system in safe mode")
            return False, failures

        # Check market data freshness
        is_fresh, reason = self.check_market_data_freshness(market_data_timestamp)
        if not is_fresh:
            failures.append(reason)

        # Check daily loss limit
        within_limit, reason = self.check_daily_loss_limit(account_equity)
        if not within_limit:
            failures.append(reason)

        # Check consecutive losses
        within_consecutive, reason = self.check_consecutive_losses()
        if not within_consecutive:
            failures.append(reason)

        # Check duplicate signal
        is_unique, reason = self.check_duplicate_signal(signal_id)
        if not is_unique:
            failures.append(reason)

        # Check max open trades
        within_trades, reason = self.check_max_open_trades(open_trade_count)
        if not within_trades:
            failures.append(reason)

        return len(failures) == 0, failures

    def get_safety_status(self) -> Dict:
        """Get current safety system status."""
        return {
            "status": self.safety_status.value,
            "circuit_breaker_active": self.circuit_breaker_active,
            "daily_pnl": self.daily_pnl,
            "consecutive_losses": self.consecutive_losses,
            "api_error_count": self.api_error_count,
            "consecutive_api_errors": self.consecutive_api_errors,
            "recent_events": self.safety_events[-10:],  # Last 10 events
        }

    # ==================== PRIVATE HELPERS ====================

    def _check_daily_reset(self) -> None:
        """Reset daily counters if new trading day."""
        now = datetime.now()

        if (now - self.session_reset_time).days > 0:
            logger.info(
                f"Daily reset | P&L: ${self.daily_pnl:.2f} | "
                f"Losses: {self.daily_loss_count}"
            )
            self.daily_pnl = 0.0
            self.daily_loss_count = 0
            self.consecutive_losses = 0
            self.circuit_breaker_active = False
            self.safety_status = SafetyStatus.ACTIVE
            self.session_reset_time = now

    def _record_event(
        self, event_type: str, severity: str, message: str
    ) -> None:
        """Record a safety event."""
        event = SafetyEvent(
            timestamp=datetime.now(),
            event_type=event_type,
            severity=severity,
            message=message,
        )
        self.safety_events.append(event)

    def _activate_circuit_breaker(self, reason: str) -> None:
        """Activate circuit breaker (disable trading)."""
        logger.critical(f"⚠️  CIRCUIT BREAKER ACTIVATED: {reason}")
        self.circuit_breaker_active = True
        self.safety_status = SafetyStatus.LOCKDOWN
        self._record_event(
            event_type="circuit_breaker",
            severity="critical",
            message=reason,
        )
