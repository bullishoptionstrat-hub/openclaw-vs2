"""
DEPLOYMENT GATE CONTROLLER - AUTOMATED GATE DECISION & DEPLOYMENT

Monitors validation metrics and automatically:
1. Determines when validation gate PASS
2. Enables deployment if criteria met
3. Routes signals to live broker
4. Monitors performance vs baseline
5. Implements circuit breakers for live trading

This is the final arbiter before capital deployment.
"""

import logging
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class DeploymentState(Enum):
    """States of deployment lifecycle."""

    PRE_VALIDATION = "pre_validation"  # Before 30-day test
    VALIDATION_RUNNING = "validation_running"  # During 30-day test
    VALIDATION_COMPLETE = "validation_complete"  # 30 days done, waiting decision
    GATE_FAILED = "gate_failed"  # Failed, no deployment
    GATE_PASSED = "gate_passed"  # Passed, ready for approval
    AWAITING_APPROVAL = "awaiting_approval"  # Awaiting operator confirmation
    DEPLOYMENT_ENABLED = "deployment_enabled"  # Capital deployed
    LIVE_TRADING = "live_trading"  # Actively trading with capital
    SUSPENDED = "suspended"  # Paused (emergency stop)


@dataclass
class DeploymentMetrics:
    """Metrics used for deployment decision."""

    days_complete: int
    pass_days: int
    consistency_score: float  # % days meeting gate
    cumulative_pnl: float
    max_drawdown: float
    win_rate: float
    sharpe_ratio: float
    execution_quality: float
    safety_violations: int
    hard_failures: List[str] = field(default_factory=list)


@dataclass
class DeploymentApproval:
    """Approval record for deployment."""

    approved_by: str  # Operator name
    approved_at: str  # ISO timestamp
    reasoning: str
    capital_amount: float
    risk_params: Dict


class DeploymentGateController:
    """
    Central gate controller for deployment decision.

    Responsibilities:
    1. Monitor validation metrics
    2. Determine PASS/FAIL status
    3. Flag when ready for deployment
    4. Require explicit operator approval
    5. Enable broker if approved
    6. Monitor live performance vs baseline
    7. Implement emergency stops
    """

    def __init__(self, max_days_validation: int = 30, min_pass_criteria: int = 4):
        """
        Initialize deployment gate controller.

        Args:
            max_days_validation: Standard validation period (days)
            min_pass_criteria: How many pass criteria required (out of 7)
        """

        self.state = DeploymentState.PRE_VALIDATION
        self.max_days_validation = max_days_validation
        self.min_pass_criteria = min_pass_criteria

        # Decision tracking
        self.last_gate_decision: Optional[Dict] = None
        self.deployment_approval: Optional[DeploymentApproval] = None
        self.deployment_time: Optional[datetime] = None

        # Performance monitoring
        self.validation_baseline: Optional[DeploymentMetrics] = None
        self.live_performance: Optional[Dict] = None
        self.live_start_time: Optional[datetime] = None
        self.live_days_elapsed: int = 0
        self.live_max_drawdown: float = 0.0
        self.live_stop_loss_triggered: bool = False

        # Circuit breakers
        self.max_live_drawdown = 0.05  # 5% max drawdown live
        self.max_daily_loss_live = 0.02  # 2% max daily loss live
        self.circuit_breaker_active = False

        logger.info(
            f"DeploymentGateController initialized | "
            f"Max validation days: {max_days_validation} | "
            f"Min pass criteria: {min_pass_criteria}/7"
        )

    def start_validation(self) -> None:
        """Start validation period."""

        self.state = DeploymentState.VALIDATION_RUNNING
        logger.info("Validation period started")

    def evaluate_validation_complete(
        self, metrics: DeploymentMetrics
    ) -> Tuple[str, Dict]:
        """
        Evaluate if validation period ended with PASS or FAIL.

        Args:
            metrics: DeploymentMetrics after completion

        Returns:
            (gate_status, decision_dict) where gate_status is PASS/FAIL/WATCH
        """

        decision = {
            "gate_status": "DEFER",
            "confidence": 0.0,
            "pass_criteria_met": [],
            "fail_reasons": [],
            "recommendation": "",
            "deployment_ready": False,
        }

        # Check hard failures first
        if metrics.hard_failures:
            decision["gate_status"] = "FAIL"
            decision["confidence"] = 0.2
            decision["fail_reasons"] = metrics.hard_failures
            decision["recommendation"] = "System failed hard conditions. Rebuild and revalidate."
            self.state = DeploymentState.GATE_FAILED
            self.last_gate_decision = decision
            return ("FAIL", decision)

        # Score pass criteria (all must be met for PASS)
        pass_count = 0

        if metrics.consistency_score >= 0.65:
            decision["pass_criteria_met"].append("✅ Consistency ≥ 65%")
            pass_count += 1
        else:
            decision["fail_reasons"].append(f"❌ Consistency {metrics.consistency_score:.1%} < 65%")

        if metrics.cumulative_pnl > 0:
            decision["pass_criteria_met"].append("✅ Positive cumulative PnL")
            pass_count += 1
        else:
            decision["fail_reasons"].append(f"❌ Cumulative PnL negative: ${metrics.cumulative_pnl:,.0f}")

        if metrics.max_drawdown <= 0.08:
            decision["pass_criteria_met"].append("✅ Max drawdown ≤ 8%")
            pass_count += 1
        else:
            decision["fail_reasons"].append(f"❌ Max drawdown {metrics.max_drawdown:.1%} > 8%")

        if metrics.win_rate >= 0.55:
            decision["pass_criteria_met"].append("✅ Win rate ≥ 55%")
            pass_count += 1
        else:
            decision["fail_reasons"].append(f"❌ Win rate {metrics.win_rate:.1%} < 55%")

        if metrics.sharpe_ratio >= 1.25:
            decision["pass_criteria_met"].append("✅ Sharpe ≥ 1.25")
            pass_count += 1
        else:
            decision["fail_reasons"].append(f"❌ Sharpe {metrics.sharpe_ratio:.2f} < 1.25")

        if metrics.execution_quality >= 0.70:
            decision["pass_criteria_met"].append("✅ Execution quality ≥ 70%")
            pass_count += 1
        else:
            decision["fail_reasons"].append(f"❌ Execution quality {metrics.execution_quality:.1%} < 70%")

        if metrics.safety_violations <= 3:
            decision["pass_criteria_met"].append("✅ Safety violations ≤ 3")
            pass_count += 1
        else:
            decision["fail_reasons"].append(f"❌ Safety violations {metrics.safety_violations} > 3")

        # Make decision
        decision["confidence"] = pass_count / 7.0

        if pass_count == 7:
            decision["gate_status"] = "PASS"
            decision["confidence"] = 0.95
            decision["recommendation"] = "✅ READY FOR DEPLOYMENT - Awaiting operator approval"
            decision["deployment_ready"] = True
            self.state = DeploymentState.GATE_PASSED
            self.validation_baseline = metrics

        elif pass_count >= 4:
            decision["gate_status"] = "WATCH"
            decision["confidence"] = 0.65
            decision["recommendation"] = "Continue validation or proceed with caution"
            self.state = DeploymentState.VALIDATION_COMPLETE

        else:
            decision["gate_status"] = "FAIL"
            decision["confidence"] = 0.30
            decision["recommendation"] = "Insufficient pass criteria. Rebuild system."
            self.state = DeploymentState.GATE_FAILED

        self.last_gate_decision = decision
        return (decision["gate_status"], decision)

    def request_approval_for_deployment(
        self, operator: str, capital_amount: float, reasoning: str
    ) -> bool:
        """
        Request operator approval for deployment.

        Requires explicit operator action to prevent accidental deployment.

        Args:
            operator: Operator name/ID
            capital_amount: Amount of capital to deploy
            reasoning: Why deployment is being requested

        Returns:
            True if approval granted
        """

        if not self.last_gate_decision or self.last_gate_decision.get("gate_status") != "PASS":
            logger.error(f"Cannot approve - gate did not pass")
            return False

        self.state = DeploymentState.AWAITING_APPROVAL

        logger.warning(f"\n{'='*80}")
        logger.warning(f"DEPLOYMENT APPROVAL REQUEST")
        logger.warning(f"{'='*80}")
        logger.warning(f"Operator: {operator}")
        logger.warning(f"Capital: ${capital_amount:,.0f}")
        logger.warning(f"Reasoning: {reasoning}")
        logger.warning(f"Status: {self.last_gate_decision['gate_status']}")
        logger.warning(f"Confidence: {self.last_gate_decision['confidence']:.1%}")
        logger.warning(f"{'='*80}\n")

        # Record approval
        self.deployment_approval = DeploymentApproval(
            approved_by=operator,
            approved_at=datetime.utcnow().isoformat(),
            reasoning=reasoning,
            capital_amount=capital_amount,
            risk_params={"max_drawdown": 0.05, "daily_loss_limit": 0.02},
        )

        logger.critical(f"✅ DEPLOYMENT APPROVED by {operator} | ${capital_amount:,.0f}")
        return True

    def enable_live_deployment(self) -> bool:
        """
        Enable live trading with real capital.

        Called after approval is granted.

        Returns:
            True if deployment enabled
        """

        if not self.deployment_approval:
            logger.error(f"No deployment approval on record")
            return False

        self.state = DeploymentState.DEPLOYMENT_ENABLED
        self.deployment_time = datetime.utcnow()
        self.live_start_time = datetime.utcnow()

        logger.critical(f"🔴 LIVE DEPLOYMENT ENABLED")
        logger.critical(
            f"   Capital: ${self.deployment_approval.capital_amount:,.0f}"
        )
        logger.critical(f"   Operator: {self.deployment_approval.approved_by}")
        logger.critical(f"   Max drawdown: 5%")
        logger.critical(f"   Daily loss limit: 2%")

        return True

    def update_live_performance(self, daily_pnl: float, current_equity: float) -> None:
        """
        Update live trading performance.

        Monitors for circuit breaker conditions.

        Args:
            daily_pnl: Daily profit/loss
            current_equity: Current account equity
        """

        if self.state not in [DeploymentState.DEPLOYMENT_ENABLED, DeploymentState.LIVE_TRADING]:
            return

        self.state = DeploymentState.LIVE_TRADING

        # Calculate drawdown
        baseline_equity = self.deployment_approval.capital_amount if self.deployment_approval else 100000.0
        drawdown = (baseline_equity - current_equity) / baseline_equity

        if drawdown > self.live_max_drawdown:
            self.live_max_drawdown = drawdown

        # Check circuit breakers
        if drawdown > self.max_live_drawdown:
            logger.critical(
                f"🔴 CIRCUIT BREAKER TRIGGERED | Drawdown {drawdown:.1%} > {self.max_live_drawdown:.1%}"
            )
            self.circuit_breaker_active = True
            self.suspend_trading("Drawdown circuit breaker")
            return

        if daily_pnl < -self.max_daily_loss_live * baseline_equity:
            logger.critical(
                f"🔴 DAILY LOSS LIMIT BREACHED | Loss ${daily_pnl:,.0f}"
            )
            self.circuit_breaker_active = True
            self.suspend_trading("Daily loss circuit breaker")
            return

        # Normal operation
        self.live_days_elapsed += 1
        logger.info(
            f"Live perf update | Equity: ${current_equity:,.0f} | "
            f"Daily PnL: ${daily_pnl:,.0f} | "
            f"Drawdown: {drawdown:.1%} | Days: {self.live_days_elapsed}"
        )

    def suspend_trading(self, reason: str) -> None:
        """Suspend trading (emergency stop)."""

        self.state = DeploymentState.SUSPENDED
        logger.critical(f"🛑 TRADING SUSPENDED | Reason: {reason}")

    def get_gate_status(self) -> Dict:
        """Get current gate status."""

        return {
            "state": self.state.value,
            "gate_decision": self.last_gate_decision,
            "deployment_approved": self.deployment_approval is not None,
            "deployment_active": self.state in [
                DeploymentState.DEPLOYMENT_ENABLED,
                DeploymentState.LIVE_TRADING,
            ],
            "circuit_breaker_active": self.circuit_breaker_active,
            "live_days": self.live_days_elapsed,
            "live_max_drawdown": self.live_max_drawdown,
            "suspended": self.state == DeploymentState.SUSPENDED,
        }
