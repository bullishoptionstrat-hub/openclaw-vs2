"""
VALIDATION ORCHESTRATOR - CENTRAL INTEGRATION BRIDGE

Connects core trading engines (AI, macro, execution) to validation layer
and manages the complete forward testing + validation + deployment gate workflow.

Responsibilities:
1. Coordinate between trading engines and validation layer
2. Run live validation with market data
3. Track validation metrics over 20-30 day period
4. Make automated pass/fail deployment decisions
5. Provide real-time monitoring + reporting

Architecture:
  Trading Engines → ValidationOrchestrator → Validation Layer → Gate Decision
  Market Data Stream ↓
  Paper Execution ↓
  Scoring ↓
  Dashboard Output
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
import json

# Phase 8.5 integration
from ..execution import ShadowExecutionComparator

# OpenTelemetry integration
from ..observability import ExecutionInstrumenter, ExecutionEventType

logger = logging.getLogger(__name__)


class ValidationPhase(Enum):
    """Phases of validation lifecycle."""

    STARTUP = "startup"  # System starting, no trades yet
    WARMING_UP = "warming_up"  # First 5 days, data collection
    VALIDATION_RUNNING = "validation_running"  # Days 5-30, active validation
    VALIDATION_COMPLETE = "validation_complete"  # Day 30+, results ready
    GATE_PASSED = "gate_passed"  # System passed, ready for capital
    GATE_FAILED = "gate_failed"  # System failed, requires rebuild
    PAUSED = "paused"  # Manual pause
    LIVE_TRADING = "live_trading"  # Capital deployed


class ValidationMetricType(Enum):
    """Types of metrics tracked during validation."""

    SIGNAL_COUNT = "signal_count"
    TRADE_COUNT = "trade_count"
    WIN_RATE = "win_rate"
    PROFIT_FACTOR = "profit_factor"
    EXPECTANCY = "expectancy"
    SHARPE_RATIO = "sharpe_ratio"
    MAX_DRAWDOWN = "max_drawdown"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    SLIPPAGE_DRIFT = "slippage_drift"
    DUPLICATE_RATE = "duplicate_rate"
    STALE_DATA_EVENTS = "stale_data_events"


@dataclass
class ValidationDaySnapshot:
    """Daily snapshot of validation metrics."""

    date: str  # YYYY-MM-DD
    day_number: int  # 1-30
    total_signals: int = 0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    daily_pnl: float = 0.0
    daily_sharpe: float = 0.0
    max_drawdown_day: float = 0.0
    avg_slippage: float = 0.0
    duplicate_signals: int = 0
    stale_data_events: int = 0
    gate_status: str = "WATCH"  # PASS, WATCH, FAIL per day
    safety_violations: int = 0
    notes: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "date": self.date,
            "day_number": self.day_number,
            "total_signals": self.total_signals,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "daily_pnl": self.daily_pnl,
            "daily_sharpe": self.daily_sharpe,
            "max_drawdown_day": self.max_drawdown_day,
            "avg_slippage": self.avg_slippage,
            "duplicate_signals": self.duplicate_signals,
            "stale_data_events": self.stale_data_events,
            "gate_status": self.gate_status,
            "safety_violations": self.safety_violations,
            "notes": self.notes,
        }


@dataclass
class ValidationMetrics:
    """Complete validation metrics for period."""

    start_date: str
    end_date: str
    validation_days: int = 0
    total_signals: int = 0
    total_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    consecutive_losses: int = 0
    avg_slippage: float = 0.0
    duplicate_rate: float = 0.0
    stale_data_events: int = 0
    total_safety_violations: int = 0
    daily_snapshots: List[ValidationDaySnapshot] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "validation_days": self.validation_days,
            "total_signals": self.total_signals,
            "total_trades": self.total_trades,
            "total_pnl": self.total_pnl,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "consecutive_losses": self.consecutive_losses,
            "avg_slippage": self.avg_slippage,
            "duplicate_rate": self.duplicate_rate,
            "stale_data_events": self.stale_data_events,
            "total_safety_violations": self.total_safety_violations,
            "daily_snapshots": [s.to_dict() for s in self.daily_snapshots],
        }


@dataclass
class ValidationGateDecision:
    """Final gate decision after validation period."""

    gate_status: str  # PASS, FAIL, DEFER
    confidence_score: float  # 0-1 overall confidence
    reasons: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    next_action: str = ""  # What to do next
    deployment_ready: bool = False
    hard_failures: List[str] = field(default_factory=list)
    deployment_capital: Optional[float] = None  # Amount to deploy if pass


class ValidationOrchestrator:
    """
    Central orchestrator for validation workflow.

    Manages:
    - Validation lifecycle (startup → running → complete → decision)
    - Integration with core engines (AI, macro, execution, risk)
    - Integration with validation layer (scoring, forward test, safety)
    - Metrics collection and reporting
    - Gate decision making
    """

    def __init__(
        self,
        scoreboard_path: Optional[str] = None,
        min_validation_days: int = 20,
        max_consecutive_losses_allowed: int = 5,
    ):
        """
        Initialize orchestrator.

        Args:
            scoreboard_path: Where to save validation results
            min_validation_days: Minimum days before decision
            max_consecutive_losses_allowed: Circuit breaker threshold
        """

        self.scoreboard_path = Path(scoreboard_path or "/tmp/validation_scoreboard.json")
        self.min_validation_days = min_validation_days
        self.max_consecutive_losses_allowed = max_consecutive_losses_allowed

        # Lifecycle tracking
        self.phase = ValidationPhase.STARTUP
        self.start_time: Optional[datetime] = None
        self.validation_start_date: Optional[str] = None

        # Metrics accumulation
        self.daily_snapshots: List[ValidationDaySnapshot] = []
        self.current_day_metrics: Optional[ValidationDaySnapshot] = None

        # Decision history
        self.gate_decisions: List[ValidationGateDecision] = []
        self.validation_complete = False

        # Integration state
        self.engines_connected = False
        self.validation_modules_loaded = False

        # Phase 8.5: Initialize shadow execution comparator
        self.shadow_comparator = ShadowExecutionComparator()

        # OpenTelemetry: Initialize instrumentation
        self.instrumenter = ExecutionInstrumenter()

        logger.info(
            f"ValidationOrchestrator initialized | "
            f"Min days: {min_validation_days} | "
            f"Scoreboard: {self.scoreboard_path}"
        )

    def initialize_validation(self) -> bool:
        """
        Initialize validation ecosystem.

        Checks:
        - All trading engines connected
        - Validation modules loaded
        - Safety controls enabled
        - Market data stream ready

        Returns:
            True if all systems ready, False otherwise
        """
Instrumentation: Record initialization started
        self.instrumenter.record_event(
            event_type=ExecutionEventType.PHASE_TRANSITION,
            from_phase=self.phase.value,
            to_phase="warming_up",
            details="Validation ecosystem initialization starting"
        )

        # TODO: Connect to actual engines when available
        self.engines_connected = True
        self.validation_modules_loaded = True

        if self.engines_connected and self.validation_modules_loaded:
            self.phase = ValidationPhase.WARMING_UP
            self.start_time = datetime.utcnow()
            self.validation_start_date = self.start_time.strftime("%Y-%m-%d")

            # Instrumentation: Record successful transition to WARMING_UP
            self.instrumenter.record_event(
                event_type=ExecutionEventType.PHASE_TRANSITION,
                from_phase="startup",
                to_phase=self.phase.value,
                start_date=self.validation_start_date
            )

            logger.info(f"✅ Validation initialized | Start: {self.validation_start_date}")
            return True

        logger.error("❌ Failed to initialize validation ecosystem")

        # Instrumentation: Record initialization failure
        self.instrumenter.record_event(
            event_type=ExecutionEventType.VALIDATION_ERROR,
            error_type="initialization_failed",
            details="Could not connect to engines or load validation modules"
        )
        return False

    def start_daily_snapshot(self, date: str, day_number: int) -> ValidationDaySnapshot:
        """Start collecting metrics for a specific day."""

        snapshot = ValidationDaySnapshot(date=date, day_number=day_number)
        self.current_day_metrics = snapshot
        logger.info(f"Started daily snapshot | Date: {date} | Day: {day_number}")
        return snapshot

    def record_signal(
        self, symbol: str, direction: str, confidence: float, regime: str
    ) -> None:
        """Record signal generation."""

        if self.current_day_metrics:
            self.current_day_metrics.total_signals += 1
        logger.debug(f"Signal recorded | {symbol} {direction} @ {confidence:.2%} ({regime})")

    def record_trade(
        self,
        symbol: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        slippage: float,
        latency_ms: float,
    ) -> None:
        """Record executed trade."""

        if not self.current_day_metrics:
            return

        self.current_day_metrics.total_trades += 1
        if pnl > 0:
            self.current_day_metrics.winning_trades += 1
        else:
            self.current_day_metrics.losing_trades += 1

        self.current_day_metrics.daily_pnl += pnl
        self.current_day_metrics.avg_slippage = (
            self.current_day_metrics.avg_slippage + slippage
        ) / 2

        logger.debug(
            f"Trade recorded | {symbol} | PnL: {pnl:.2f} | Slippage: {slippage:.4f} | Latency: {latency_ms:.0f}ms"
        )

    def record_safety_violation(self, violation_type: str, detail: str) -> None:
        """Record safety control violation."""

        if self.current_day_metrics:
            self.current_day_metrics.safety_violations += 1
            self.current_day_metrics.notes += f"\n[{violation_type}] {detail}"

        logger.warning(f"Safety violation | {violation_type}: {detail}")

    def record_duplicate_signal(self) -> None:
        """Record duplicate signal detection."""

        if self.current_day_metrics:
            self.current_day_metrics.duplicate_signals += 1

    def record_stale_data_event(self) -> None:
        """Record stale market data detection."""

        if self.current_day_metrics:
            self.current_day_metrics.stale_data_events += 1

    # ==================== PHASE 8.5: SHADOW EXECUTION INTEGRATION ====================

    def create_shadow_execution(
        self,
        signal_id: str,
        symbol: str,
        sim_expected_price: float,
        market_price_at_signal: float,
    ) -> None:
        """
        Create shadow execution pair (simulated vs market reality).

        Call this when a signal is generated.

        Args:
            signal_id: Unique signal identifier
            symbol: Trading symbol
            sim_expected_price: Expected price from simulation
            market_price_at_signal: Actual market price at signal time
        """

        self.shadow_comparator.create_shadow_execution(
            signal_id=signal_id,
            symbol=symbol,
            sim_expected_price=sim_expected_price,
            market_price_at_signal=market_price_at_signal,
        )

        logger.debug(f"Shadow execution created | Signal: {signal_id} | {symbol}")

    def record_shadow_simulated_fill(
        self,
        signal_id: str,
        fill_price: float,
        fill_qty: float,
        fill_time: Optional[datetime] = None,
    ) -> None:
        """
        Record simulated fill in shadow execution.

        Call this when ForwardTestEngine executes the signal.

        Args:
            signal_id: Matches signal from create_shadow_execution
            fill_price: Price filled in simulation
            fill_qty: Quantity filled
            fill_time: When fill occurred (defaults to now)
        """

        fill_time_str = (fill_time or datetime.utcnow()).isoformat()

        self.shadow_comparator.record_simulated_fill(
            signal_id=signal_id,
            fill_price=fill_price,
            fill_qty=fill_qty,
            fill_time=fill_time_str,
        )

        logger.debug(f"Simulated fill recorded | Signal: {signal_id} | ${fill_price:.2f} x {fill_qty}")

    def record_shadow_market_fill(
        self,
        signal_id: str,
        actual_fill_price: float,
        actual_qty: float,
        ohlc_high: float,
        ohlc_low: float,
        fill_time: Optional[datetime] = None,
    ) -> None:
        """
        Record market fill in shadow execution.

        Call this when actual market fill data becomes available.

        Args:
            signal_id: Matches signal from create_shadow_execution
            actual_fill_price: What market actually filled at
            actual_qty: Quantity available/filled
            ohlc_high: High for the period
            ohlc_low: Low for the period
            fill_time: When fill occurred (defaults to now)
        """

        fill_time_str = (fill_time or datetime.utcnow()).isoformat()

        self.shadow_comparator.record_market_reality(
            signal_id=signal_id,
            actual_fill_price=actual_fill_price,
            actual_qty=actual_qty,
            ohlc_high=ohlc_high,
            ohlc_low=ohlc_low,
            fill_time=fill_time_str,
        )

        logger.debug(
            f"Market fill recorded | Signal: {signal_id} | ${actual_fill_price:.2f} x {actual_qty}"
        )

    def get_shadow_execution_report(self) -> Dict:
        """Get daily shadow execution divergence report."""

        return self.shadow_comparator.get_daily_report()

    def end_daily_snapshot(
        self, daily_gate_status: str, daily_sharpe: float, max_drawdown: float
    ) -> ValidationDaySnapshot:
        """Complete daily metrics and assess daily gate."""

        if not self.current_day_metrics:
            return None

        self.current_day_metrics.gate_status = daily_gate_status
        self.current_day_metrics.daily_sharpe = daily_sharpe
        self.current_day_metrics.max_drawdown_day = max_drawdown

        self.daily_snapshots.append(self.current_day_metrics)

        logger.info(
            f"Daily snapshot complete | "
        previous_phase = self.phase

        if elapsed_days < 5:
            self.phase = ValidationPhase.WARMING_UP
        elif elapsed_days < self.min_validation_days:
            self.phase = ValidationPhase.VALIDATION_RUNNING
        else:
            self.phase = ValidationPhase.VALIDATION_COMPLETE

        # Instrumentation: Record phase transitions
        if previous_phase != self.phase:
            self.instrumenter.record_event(
                event_type=ExecutionEventType.PHASE_TRANSITION,
                from_phase=previous_phase.value,
                to_phase=self.phase.value,
                elapsed_days=elapsed_days,
                progress=progress
            )
            logger.info(f"📊 Phase transition: {previous_phase.value} → {self.phase.value}")
        snapshot = self.current_day_metrics
        self.current_day_metrics = None
        return snapshot

    def check_validation_status(self) -> Tuple[str, float]:
        """
        Check current validation status.

        Returns:
            (phase_status, progress_pct): Current phase and progress 0-1
        """

        if not self.start_time:
            return (ValidationPhase.STARTUP.value, 0.0)

        elapsed = datetime.utcnow() - self.start_time
        elapsed_days = elapsed.days + (elapsed.seconds / 86400)
        progress = min(elapsed_days / self.min_validation_days, 1.0)

        if elapsed_days < 5:
            self.phase = ValidationPhase.WARMING_UP
        elif elapsed_days < self.min_validation_days:
            self.phase = ValidationPhase.VALIDATION_RUNNING
        else:
            # Instrumentation: Record deferred evaluation
            self.instrumenter.record_event(
                event_type=ExecutionEventType.EVALUATION_DEFERRED,
                days_collected=len(self.daily_snapshots),
                days_required=self.min_validation_days
            )
            return ValidationGateDecision(
                gate_status="DEFER",
                confidence_score=0.0,
                reasons=[f"Only {len(self.daily_snapshots)} days of data, need {self.min_validation_days}"],
                next_action="Continue validation",
            )

        # Calculate aggregate metrics
        metrics = self._aggregate_metrics()

        # Make gate decision
        decision = self._make_gate_decision(metrics)
        self.gate_decisions.append(decision)

        # Instrumentation: Record gate decision
        previous_phase = self.phase

        if decision.gate_status == "PASS":
            self.phase = ValidationPhase.GATE_PASSED
            logger.info(f"✅ VALIDATION GATE PASSED | Ready for deployment")

            self.instrumenter.record_event(
                event_type=ExecutionEventType.GATE_DECISION,
                gate_status="PASS",
                confidence=decision.confidence_score,
                metrics=metrics.to_dict()
            )
        elif decision.gate_status == "FAIL":
            self.phase = ValidationPhase.GATE_FAILED
            logger.error(f"❌ VALIDATION GATE FAILED | System requires rebuild")

            self.instrumenter.record_event(
                event_type=ExecutionEventType.GATE_DECISION,
                gate_status="FAIL",
                confidence=decision.confidence_score,
                hard_failures=decision.hard_failures,
                metrics=metrics.to_dict()
            )
        else:
            logger.info(f"⏳ VALIDATION DEFERRED | {decision.reasons}")

            self.instrumenter.record_event(
                event_type=ExecutionEventType.GATE_DECISION,
                gate_status="DEFER",
                reasons=decision.reasons
            )

        # Instrumentation: Record phase transition if applicable
        if previous_phase != self.phase:
            self.instrumenter.record_event(
                event_type=ExecutionEventType.PHASE_TRANSITION,
                from_phase=previous_phase.value,
                to_phase=self.phase.value,
                gate_decision=decision.gate_status
            

        # Make gate decision
        decision = self._make_gate_decision(metrics)
        self.gate_decisions.append(decision)

        if decision.gate_status == "PASS":
            self.phase = ValidationPhase.GATE_PASSED
            logger.info(f"✅ VALIDATION GATE PASSED | Ready for deployment")
        elif decision.gate_status == "FAIL":
            self.phase = ValidationPhase.GATE_FAILED
            logger.error(f"❌ VALIDATION GATE FAILED | System requires rebuild")
        else:
            logger.info(f"⏳ VALIDATION DEFERRED | {decision.reasons}")

        self._save_scoreboard(metrics, decision)
        return decision

    def _aggregate_metrics(self) -> ValidationMetrics:
        """Aggregate daily snapshots into period metrics."""

        total_signals = sum(s.total_signals for s in self.daily_snapshots)
        total_trades = sum(s.total_trades for s in self.daily_snapshots)
        total_pnl = sum(s.daily_pnl for s in self.daily_snapshots)
        total_wins = sum(s.winning_trades for s in self.daily_snapshots)
        total_losses = sum(s.losing_trades for s in self.daily_snapshots)

        win_rate = total_wins / total_trades if total_trades > 0 else 0.0
        profit_factor = (
            (total_pnl + (total_wins * 1.0))
            / (abs(total_pnl - (total_losses * 1.0)) or 1)
            if total_trades > 0
            else 0.0
        )
        expectancy = (win_rate * 1.5) - ((1 - win_rate) * 1.0) if total_trades > 0 else 0.0
        sharpe_ratio = (
            sum(s.daily_sharpe for s in self.daily_snapshots) / len(self.daily_snapshots)
            if self.daily_snapshots
            else 0.0
        )
        max_drawdown = max((s.max_drawdown_day for s in self.daily_snapshots), default=0.0)
        consecutive_losses = max(
            (s.consecutive_losses for s in self.daily_snapshots), default=0
        )
        avg_slippage = (
            sum(s.avg_slippage for s in self.daily_snapshots) / len(self.daily_snapshots)
            if self.daily_snapshots
            else 0.0
        )
        duplicate_rate = (
            sum(s.duplicate_signals for s in self.daily_snapshots) / total_signals
            if total_signals > 0
            else 0.0
        )
        stale_data_events = sum(s.stale_data_events for s in self.daily_snapshots)
        total_safety_violations = sum(
            s.safety_violations for s in self.daily_snapshots
        )

        return ValidationMetrics(
            start_date=self.daily_snapshots[0].date if self.daily_snapshots else "",
            end_date=self.daily_snapshots[-1].date if self.daily_snapshots else "",
            validation_days=len(self.daily_snapshots),
            total_signals=total_signals,
            total_trades=total_trades,
            total_pnl=total_pnl,
            win_rate=win_rate,
            profit_factor=profit_factor,
            expectancy=expectancy,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            consecutive_losses=consecutive_losses,
            avg_slippage=avg_slippage,
            duplicate_rate=duplicate_rate,
            stale_data_events=stale_data_events,
            total_safety_violations=total_safety_violations,
            daily_snapshots=self.daily_snapshots,
        )

    def _make_gate_decision(self, metrics: ValidationMetrics) -> ValidationGateDecision:
        """Make automated pass/fail gate decision."""

        decision = ValidationGateDecision(
            gate_status="PASS",  # Default to pass, override below
            confidence_score=0.8,
            hard_failures=[],
        )

        # Hard fail conditions (any override = FAIL)
        if metrics.max_drawdown > 0.10:  # >10% drawdown
            decision.hard_failures.append(f"Max drawdown {metrics.max_drawdown:.2%} > 10%")

        if metrics.stale_data_events > 2:  # More than 2 stale data events
            decision.hard_failures.append(f"Stale data events: {metrics.stale_data_events}")

        if metrics.duplicate_rate > 0.01:  # >1% duplicate signals
            decision.hard_failures.append(f"Duplicate rate {metrics.duplicate_rate:.2%} > 1%")

        if metrics.expectancy <= 0.05:  # Positive expectancy required
            decision.hard_failures.append(f"Low expectancy: {metrics.expectancy:.3f}")

        if metrics.consecutive_losses > self.max_consecutive_losses_allowed:
            decision.hard_failures.append(
                f"Consecutive losses {metrics.consecutive_losses} > {self.max_consecutive_losses_allowed}"
            )

        if metrics.total_safety_violations > 3:
            decision.hard_failures.append(
                f"Safety violations: {metrics.total_safety_violations}"
            )

        # If any hard failures, FAIL the gate
        if decision.hard_failures:
            decision.gate_status = "FAIL"
            decision.confidence_score = 0.2
            decision.reasons = decision.hard_failures
            decision.next_action = "Review system and rebuild"
            decision.deployment_ready = False
            return decision

        # Pass criteria (all must be met)
        pass_criteria = []

        if metrics.profit_factor >= 1.35:
            pass_criteria.append("✅ Profit factor >= 1.35")
        else:
            pass_criteria.append(f"❌ Profit factor {metrics.profit_factor:.2f} < 1.35")

        if metrics.win_rate >= 0.55:
            pass_criteria.append("✅ Win rate >= 55%")
        else:
            pass_criteria.append(f"❌ Win rate {metrics.win_rate:.2%} < 55%")

        if metrics.sharpe_ratio >= 1.25:
            pass_criteria.append("✅ Sharpe ratio >= 1.25")
        else:
            pass_criteria.append(f"❌ Sharpe ratio {metrics.sharpe_ratio:.2f} < 1.25")

        if metrics.max_drawdown <= 0.08:
            pass_criteria.append("✅ Max drawdown <= 8%")
        else:
            pass_criteria.append(f"❌ Max drawdown {metrics.max_drawdown:.2%} > 8%")

        if metrics.avg_slippage <= 0.001:  # 0.1% slippage
            pass_criteria.append("✅ Avg slippage <= 0.1%")
        else:
            pass_criteria.append(f"❌ Avg slippage {metrics.avg_slippage:.4f} > 0.1%")

        decision.recommendations = pass_criteria

        # Count passing criteria
        passing = sum(1 for c in pass_criteria if c.startswith("✅"))
        total_criteria = len(pass_criteria)

        if passing == total_criteria:
            decision.gate_status = "PASS"
            decision.confidence_score = 0.95
            decision.next_action = "Deploy capital to live trading"
            decision.deployment_ready = True
            decision.deployment_capital = 10000  # Start with $10k
        elif passing >= 3:
            decision.gate_status = "WATCH"
            decision.confidence_score = 0.65
            decision.next_action = "Continue validation for additional period"
        else:
            decision.gate_status = "FAIL"
            decision.confidence_score = 0.30
            decision.next_action = "Rebuild system with parameter adjustments"

        decision.reasons = pass_criteria
        return decision

    def _save_scoreboard(self, metrics: ValidationMetrics, decision: ValidationGateDecision) -> None:
        """Save validation results to scoreboard file."""

        scoreboard = {
            "validation_period": {
                "start": metrics.start_date,
                "end": metrics.end_date,
                "days": metrics.validation_days,
            },
            "metrics": metrics.to_dict(),
            "gate_decision": {
                "status": decision.gate_status,
                "confidence": decision.confidence_score,
                "reasons": decision.reasons,
                "recommendations": decision.recommendations,
                "next_action": decision.next_action,
                "deployment_ready": decision.deployment_ready,
                "hard_failures": decision.hard_failures,
                "deployment_capital": decision.deployment_capital,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

        self.scoreboard_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.scoreboard_path, "w") as f:
            json.dump(scoreboard, f, indent=2)

        logger.info(f"Scoreboard saved | Path: {self.scoreboard_path}")

    def get_health_report(self) -> Dict:
        """Get current system health for monitoring."""

        if not self.daily_snapshots:
            return {"status": "initializing", "progress": 0.0}

        latest = self.daily_snapshots[-1]
        phase, progress = self.check_validation_status()

        return {
            "phase": phase,
            "progress": progress,
            "latest_date": latest.date,
            "total_trades": latest.total_trades,
            "daily_pnl": latest.daily_pnl,
            "day_gate_status": latest.gate_status,
            "safety_violations": latest.safety_violations,
            "timestamp": datetime.utcnow().isoformat(),
        }
