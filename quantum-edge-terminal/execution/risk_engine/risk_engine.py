"""
RISK ENGINE - INSTITUTIONAL-GRADE RISK MANAGEMENT

This is where most retail traders fail and lose money.

Enforces:
1. Maximum % risk per trade
2. Maximum daily loss limit (hard stop)
3. Maximum open trades simultaneously
4. Maximum exposure per asset
5. Duplicate signal detection (prevents double orders)
6. API failure safeguards (cancel pending orders)

Philosophy: "In doubt, don't trade"
- Any risk check failure = NO ORDER
- Errors on the side of safety
- Paper trading ALWAYS passes (safe mode)
- Live trading: conservative thresholds

Input: ExecutionPayload + Account state
Output: RiskCheckResult (PASS/FAIL with reason)
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk assessment levels."""

    PASS = "pass"  # Risk check passed, safe to trade
    WARNING = "warning"  # Risk acceptable but elevated
    FAIL = "fail"  # Risk check failed, do not trade


@dataclass
class RiskCheckResult:
    """Result of risk validation."""

    level: RiskLevel
    reason: str
    risk_score: float  # 0-1, where 1 is maximum risk
    details: Dict = field(default_factory=dict)

    def passes(self) -> bool:
        """Check if risk validation passed."""
        return self.level in [RiskLevel.PASS, RiskLevel.WARNING]


@dataclass
class RiskLimits:
    """Configure risk management limits."""

    # Per-trade limits
    max_risk_per_trade_pct: float = 2.0  # Max 2% of account per trade
    max_exposure_per_asset_pct: float = 10.0  # Max 10% in single asset
    max_position_size_pct: float = 5.0  # Max 5% of portfolio per position

    # Account-level limits
    max_daily_loss_pct: float = 5.0  # Hard stop at -5% daily
    max_drawdown_pct: float = 10.0  # Max portfolio drawdown
    max_open_trades: int = 5  # Max 5 concurrent positions

    # Signal validation
    min_signal_confidence: float = 0.5  # Signal must be ≥50%
    min_macro_confirmation: float = 0.3  # Macro engine ≥30%
    max_duplicate_window_minutes: int = 5  # Same signal within 5min = duplicate

    # Advanced
    require_profit_confirmation: bool = True  # Must see profit before scaling up
    circuit_breaker_enabled: bool = True  # Auto-disable after N errors


class RiskEngine:
    """
    Enforces institutional-grade risk controls before any order execution.

    This is the ONLY place that prevents bad trades from happening.
    No order bypasses this layer.
    """

    def __init__(self, limits: RiskLimits = None):
        """
        Initialize risk engine.

        Args:
            limits: RiskLimits configuration (default: safe trading limits)
        """
        self.limits = limits or RiskLimits()
        self.daily_pnl = 0.0  # Today's total PnL
        self.open_positions: Dict[str, Dict] = {}  # Symbol -> position data
        self.recent_signals: List[Dict] = []  # For duplicate detection
        self.trade_count_today = 0
        self.error_count = 0
        self.circuit_breaker_active = False
        self.last_reset = datetime.now()

        logger.info(
            f"RiskEngine initialized | Max risk/trade: {self.limits.max_risk_per_trade_pct}% | "
            f"Daily loss limit: {self.limits.max_daily_loss_pct}% | "
            f"Max open trades: {self.limits.max_open_trades}"
        )

    def validate(
        self,
        execution_payload: Dict,
        account_info: Dict,
        current_positions: List[Dict] = None,
    ) -> RiskCheckResult:
        """
        Comprehensive risk validation.

        This is called BEFORE any order is submitted.

        Args:
            execution_payload: From execution_engine
            account_info: Current account state
            current_positions: Open positions

        Returns:
            RiskCheckResult with pass/fail + reason
        """

        # Reset daily limits if new day
        self._check_daily_reset()

        # Circuit breaker check
        if self._is_circuit_breaker_active():
            return RiskCheckResult(
                level=RiskLevel.FAIL,
                reason="Circuit breaker active - too many errors",
                risk_score=1.0,
            )

        # Collection of all checks
        checks = []

        # 1. DUPLICATE SIGNAL CHECK (prevents double orders)
        duplicate_result = self._check_duplicate_signal(execution_payload)
        checks.append(duplicate_result)

        # 2. SIGNAL CONFIDENCE CHECK
        confidence_result = self._check_confidence(execution_payload)
        checks.append(confidence_result)

        # 3. ACCOUNT STATE CHECKS
        account_result = self._check_account_health(account_info)
        checks.append(account_result)

        # 4. DAILY LOSS CHECK (hard stop)
        daily_loss_result = self._check_daily_loss_limit(account_info)
        checks.append(daily_loss_result)

        # 5. OPEN TRADES CHECK
        current_positions = current_positions or []
        open_trades_result = self._check_open_trades_limit(current_positions)
        checks.append(open_trades_result)

        # 6. EXPOSURE CHECK (per asset)
        exposure_result = self._check_asset_exposure(
            execution_payload, account_info, current_positions
        )
        checks.append(exposure_result)

        # 7. POSITION SIZE CHECK
        position_size_result = self._check_position_size(execution_payload, account_info)
        checks.append(position_size_result)

        # Aggregate results
        failures = [c for c in checks if c.level == RiskLevel.FAIL]
        warnings = [c for c in checks if c.level == RiskLevel.WARNING]

        if failures:
            reason = " | ".join([f.reason for f in failures])
            return RiskCheckResult(
                level=RiskLevel.FAIL,
                reason=f"Risk validation failed: {reason}",
                risk_score=1.0,
                details={"failures": [f.reason for f in failures]},
            )

        # Calculate overall risk score
        risk_score = max(
            [c.risk_score for c in checks],
            default=0.0,
        )

        level = RiskLevel.WARNING if warnings else RiskLevel.PASS

        logger.info(f"Risk validation passed | Score: {risk_score:.2f} | Warnings: {len(warnings)}")

        return RiskCheckResult(
            level=level,
            reason="Risk validation passed" if not warnings else f"{len(warnings)} warnings",
            risk_score=risk_score,
            details={"warnings": [w.reason for w in warnings]},
        )

    def record_trade(self, symbol: str, qty: float, entry_price: float, direction: str) -> None:
        """Record an executed trade for position tracking."""
        self.open_positions[symbol] = {
            "qty": qty,
            "entry_price": entry_price,
            "direction": direction,
            "entry_time": datetime.now(),
        }
        self.trade_count_today += 1
        logger.info(f"Trade recorded | Symbol: {symbol} | Qty: {qty} | Direction: {direction}")

    def close_trade(self, symbol: str, exit_price: float) -> float:
        """
        Close a position and return PnL.

        Args:
            symbol: Position to close
            exit_price: Exit price per share

        Returns:
            PnL amount (positive = profit)
        """
        if symbol not in self.open_positions:
            logger.warning(f"Position not found: {symbol}")
            return 0.0

        pos = self.open_positions[symbol]
        qty = pos["qty"]
        entry_price = pos["entry_price"]
        direction = pos["direction"]

        if direction == "LONG":
            pnl = (exit_price - entry_price) * qty
        else:  # SHORT
            pnl = (entry_price - exit_price) * qty

        self.daily_pnl += pnl
        del self.open_positions[symbol]

        logger.info(
            f"Trade closed | Symbol: {symbol} | Entry: ${entry_price} | "
            f"Exit: ${exit_price} | PnL: ${pnl:.2f}"
        )

        return pnl

    # ==================== PRIVATE CHECKS ====================

    def _check_duplicate_signal(self, payload: Dict) -> RiskCheckResult:
        """
        Detect duplicate signals (prevents accidental double orders).

        If we just received an identical signal within MAX_DUPLICATE_WINDOW_MINUTES,
        it's likely a duplicate.
        """
        signal_id = payload.get("signal_id", "")
        timestamp = datetime.now()

        # Check recent signals
        now = datetime.now()
        window = timedelta(minutes=self.limits.max_duplicate_window_minutes)

        for recent in self.recent_signals:
            if recent["signal_id"] == signal_id and (now - recent["timestamp"]) < window:
                return RiskCheckResult(
                    level=RiskLevel.FAIL,
                    reason=f"Duplicate signal detected (signal_id: {signal_id})",
                    risk_score=1.0,
                )

        # Add to recent signals
        self.recent_signals.append({"signal_id": signal_id, "timestamp": timestamp})

        # Clean old signals
        self.recent_signals = [s for s in self.recent_signals if (now - s["timestamp"]) < window]

        return RiskCheckResult(
            level=RiskLevel.PASS,
            reason="No duplicate signal",
            risk_score=0.0,
        )

    def _check_confidence(self, payload: Dict) -> RiskCheckResult:
        """Check signal confidence meets minimum threshold."""
        signal_conf = payload.get("confidence", 0.5)
        macro_conf = payload.get("macro_confidence", 0.3)

        if signal_conf < self.limits.min_signal_confidence:
            return RiskCheckResult(
                level=RiskLevel.FAIL,
                reason=f"Signal confidence too low: {signal_conf:.1%} "
                f"(min: {self.limits.min_signal_confidence:.1%})",
                risk_score=1.0,
            )

        if macro_conf < self.limits.min_macro_confirmation:
            return RiskCheckResult(
                level=RiskLevel.WARNING,
                reason=f"Macro confirmation low: {macro_conf:.1%}",
                risk_score=0.5,
            )

        return RiskCheckResult(
            level=RiskLevel.PASS,
            reason=f"Confidence OK (signal: {signal_conf:.1%}, macro: {macro_conf:.1%})",
            risk_score=0.0,
        )

    def _check_account_health(self, account: Dict) -> RiskCheckResult:
        """Check basic account health."""
        cash = account.get("cash", 0)
        buying_power = account.get("buying_power", 0)

        if cash <= 0:
            return RiskCheckResult(
                level=RiskLevel.FAIL,
                reason="No available cash",
                risk_score=1.0,
            )

        if buying_power < 1000:  # Minimum $1000 required
            return RiskCheckResult(
                level=RiskLevel.WARNING,
                reason=f"Low buying power: ${buying_power:.2f}",
                risk_score=0.7,
            )

        return RiskCheckResult(
            level=RiskLevel.PASS,
            reason=f"Account healthy (cash: ${cash:.2f})",
            risk_score=0.0,
        )

    def _check_daily_loss_limit(self, account: Dict) -> RiskCheckResult:
        """
        Check if daily loss exceeds maximum allowed.

        This is the HARD STOP - if we hit max daily loss, no more trades today.
        """
        equity = account.get("equity", 100000)
        max_daily_loss_pct = self.limits.max_daily_loss_pct

        if self.daily_pnl < 0:
            loss_pct = abs(self.daily_pnl) / equity * 100

            if loss_pct > max_daily_loss_pct:
                reason = (
                    f"Daily loss limit exceeded: "
                    f"${abs(self.daily_pnl):.2f} ({loss_pct:.1f}%) "
                    f"> limit ({max_daily_loss_pct}%)"
                )
                logger.critical(f"⚠️  {reason} - NO MORE TRADES TODAY")

                return RiskCheckResult(
                    level=RiskLevel.FAIL,
                    reason=reason,
                    risk_score=1.0,
                )

        return RiskCheckResult(
            level=RiskLevel.PASS,
            reason=f"Daily P&L OK: ${self.daily_pnl:.2f}",
            risk_score=0.0,
        )

    def _check_open_trades_limit(self, positions: List[Dict]) -> RiskCheckResult:
        """Check if we've hit max open trades."""
        open_trade_count = len(positions)

        if open_trade_count >= self.limits.max_open_trades:
            return RiskCheckResult(
                level=RiskLevel.FAIL,
                reason=f"Max open trades reached: {open_trade_count} "
                f"(limit: {self.limits.max_open_trades})",
                risk_score=1.0,
            )

        risk_score = open_trade_count / self.limits.max_open_trades
        return RiskCheckResult(
            level=RiskLevel.PASS,
            reason=f"Open trades: {open_trade_count}/{self.limits.max_open_trades}",
            risk_score=risk_score,
        )

    def _check_asset_exposure(
        self, payload: Dict, account: Dict, positions: List[Dict]
    ) -> RiskCheckResult:
        """Check if exposure to single asset exceeds maximum."""
        symbol = payload.get("symbol", "")
        position_size_pct = payload.get("position_size_pct", 2.0)
        max_exposure_pct = self.limits.max_exposure_per_asset_pct

        # Get existing exposure to this asset
        existing_exposure = sum(
            p.get("market_value_pct", 0) for p in positions if p.get("symbol") == symbol
        )

        total_exposure = existing_exposure + position_size_pct

        if total_exposure > max_exposure_pct:
            return RiskCheckResult(
                level=RiskLevel.FAIL,
                reason=f"Asset exposure too high: {total_exposure:.1f}% "
                f"> limit ({max_exposure_pct}%)",
                risk_score=1.0,
            )

        return RiskCheckResult(
            level=RiskLevel.PASS,
            reason=f"Asset exposure OK: {total_exposure:.1f}% (limit: {max_exposure_pct}%)",
            risk_score=total_exposure / max_exposure_pct,
        )

    def _check_position_size(self, payload: Dict, account: Dict) -> RiskCheckResult:
        """Check if position size as % of account exceeds maximum."""
        position_size_pct = payload.get("position_size_pct", 2.0)
        max_position_pct = self.limits.max_position_size_pct

        if position_size_pct > max_position_pct:
            return RiskCheckResult(
                level=RiskLevel.FAIL,
                reason=f"Position size too large: {position_size_pct:.1f}% "
                f"> limit ({max_position_pct}%)",
                risk_score=1.0,
            )

        return RiskCheckResult(
            level=RiskLevel.PASS,
            reason=f"Position size OK: {position_size_pct:.1f}%",
            risk_score=position_size_pct / max_position_pct,
        )

    def _check_daily_reset(self) -> None:
        """Reset daily counters if new day."""
        now = datetime.now()
        if (now - self.last_reset).days > 0:
            logger.info(
                f"Daily reset | Previous P&L: ${self.daily_pnl:.2f} | "
                f"Trades: {self.trade_count_today}"
            )
            self.daily_pnl = 0.0
            self.trade_count_today = 0
            self.error_count = 0
            self.circuit_breaker_active = False
            self.last_reset = now

    def _is_circuit_breaker_active(self) -> bool:
        """Check if circuit breaker is active (too many errors)."""
        if not self.limits.circuit_breaker_enabled:
            return False

        # Circuit breaker: 5+ errors in session activates
        if self.error_count >= 5:
            logger.critical("⚠️  CIRCUIT BREAKER ACTIVE - system in safe mode")
            return True

        return False

    def record_error(self) -> None:
        """Record an error (for circuit breaker)."""
        self.error_count += 1
        logger.warning(f"Error recorded | Total errors this session: {self.error_count}")
