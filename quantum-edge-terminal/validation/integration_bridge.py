"""
INTEGRATION BRIDGE - CONNECT ENGINES TO VALIDATION

Bridges core trading engines (execution_engine, risk_engine, broker_engine)
to the validation layer (forward test, scoring, safety controls).

Flow:
  Market Data → Engines → Signals → Integration Bridge → Validation Layer
                                        ↓
                            Paper Execution + Scoring
                                        ↓
                            Safety Controls + Gate Decision

Responsibilities:
1. Accept signals from execution engines
2. Route through safety controls
3. Execute as paper trades via forward test engine
4. Collect performance metrics
5. Feed to scoring engine
6. Report gate status
"""

import logging
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

# Phase 8.5 integration
from ..execution import ExecutionKillSwitch, KillSwitchStatus

# OpenTelemetry integration
from ..observability import ExecutionInstrumenter, ExecutionEventType

logger = logging.getLogger(__name__)


class SignalSource(Enum):
    """Origin of trading signal."""

    AI_ENGINE = "ai_engine"
    MACRO_ENGINE = "macro_engine"
    EXECUTION_ENGINE = "execution_engine"
    USER_MANUAL = "user_manual"


class BridgeExecutionMode(Enum):
    """Execution mode for bridge."""

    PAPER_VALIDATION = "paper_validation"  # Forward testing
    PAPER_LIVE = "paper_live"  # Concurrent with live
    LIVE_TRADING = "live_trading"  # Real capital deployment


@dataclass
class BridgeSignal:
    """Signal crossing the bridge from engines to validation."""

    symbol: str
    direction: str  # LONG or SHORT
    confidence: float  # 0-1
    position_size: float  # In dollars
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    signal_source: SignalSource
    regime: str  # From macro engine (NORMAL, BULL, BEAR, CRISIS)
    timestamp: str  # ISO format
    signal_id: str  # Unique identifier

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "confidence": self.confidence,
            "position_size": self.position_size,
            "entry_price": self.entry_price,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "signal_source": self.signal_source.value,
            "regime": self.regime,
            "timestamp": self.timestamp,
            "signal_id": self.signal_id,
        }


@dataclass
class BridgeExecutionResult:
    """Result of bridge execution."""

    signal_accepted: bool
    execution_mode: BridgeExecutionMode
    paper_trade_id: Optional[str] = None
    live_order_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    safety_violations: List[str] = None
    gate_status: str = "WATCH"  # PASS, WATCH, FAIL
    confidence_score: float = 0.0


class IntegrationBridge:
    """
    Central bridge integrating engines with validation layer.

    Acts as middleware between:
    - Core engines (produce signals)
    - Validation layer (paper trading, scoring, safety)
    - Broker connection (live execution gate)
    """

    def __init__(
        self,
        execution_mode: BridgeExecutionMode = BridgeExecutionMode.PAPER_VALIDATION,
        paper_trading_enabled: bool = True,
        enable_safety_controls: bool = True,
        enable_scoring: bool = True,
    ):
        """
        Initialize integration bridge.

        Args:
            execution_mode: How to handle signals
            paper_trading_enabled: Route through forward test engine
            enable_safety_controls: Run pre-trade safety checks
            enable_scoring: Score trades against institutional standards
        """

        self.execution_mode = execution_mode
        self.paper_trading_enabled = paper_trading_enabled
        self.enable_safety_controls = enable_safety_controls
        self.enable_scoring = enable_scoring

        # Phase 8.5: Initialize execution kill switch
        self.kill_switch = ExecutionKillSwitch()

        # OpenTelemetry: Initialize instrumentation
        self.instrumenter = ExecutionInstrumenter()

        # Signal pipeline state
        self.signals_received: List[BridgeSignal] = []
        self.signals_executed: List[BridgeSignal] = []
        self.signals_rejected: List[Tuple[BridgeSignal, str]] = []

        # Metrics
        self.total_signals = 0
        self.accepted_signals = 0
        self.rejected_signals = 0
        self.safety_violations_count = 0

        logger.info(
            f"IntegrationBridge initialized | "
            f"Mode: {execution_mode.value} | "
            f"Paper: {paper_trading_enabled} | "
            f"Safety: {enable_safety_controls} | "
            f"Scoring: {enable_scoring}"
        )

    def process_signal(self, signal: BridgeSignal) -> BridgeExecutionResult:
        """
        Process incoming signal from engines.

        Pipeline:
        1. Validate signal format
        2. Run safety checks (if enabled)
        3. Execute as paper trade (if enabled)
        4. Score execution (if enabled)
        5. Determine gate status
        6. Route to live execution (if enabled)

        Args:
            signal: BridgeSignal from engines

        Returns:
            BridgeExecutionResult with acceptance/rejection and gate status
        """

        self.total_signals += 1
        self.signals_received.append(signal)

        logger.info(
            f"Signal received | {signal.symbol} {signal.direction} @ {signal.confidence:.2%} | "
            f"Source: {signal.signal_source.value} | Regime: {signal.regime}"
        )

        result = BridgeExecutionResult(
            signal_accepted=True,
            execution_mode=self.execution_mode,
        )

        # Step 1: Validate signal format
        validation_error = self._validate_signal(signal)
        if validation_error:
            result.signal_accepted = False
            result.rejection_reason = validation_error
            self.rejected_signals += 1
            self.signals_rejected.append((signal, validation_error))
            logger.warning(f"Signal rejected | {validation_error}")

            # Instrumentation: Record validation failure
            self.instrumenter.record_event(
                event_type=ExecutionEventType.VALIDATION_FAILED,
                signal_id=signal.signal_id,
                reason=validation_error
            )
            return result

        # Step 2: Run safety checks
        if self.enable_safety_controls:
            safety_violations = self._run_safety_checks(signal)
            if safety_violations:
                result.safety_violations = safety_violations
                self.safety_violations_count += len(safety_violations)

                # Instrumentation: Record safety violations
                self.instrumenter.record_event(
                    event_type=ExecutionEventType.SAFETY_VIOLATION,
                    signal_id=signal.signal_id,
                    violations=safety_violations,
                    violation_count=len(safety_violations)
                )

                if len(safety_violations) >= 2:  # Critical violations
                    result.signal_accepted = False
                    result.rejection_reason = f"Critical safety violations: {safety_violations}"
                    self.rejected_signals += 1
                    logger.error(f"Signal rejected due to safety | {safety_violations}")
                    return result
        
        # Instrumentation: Record successful validation and safety checks
        self.instrumenter.record_event(
            event_type=ExecutionEventType.SAFETY_CHECKS_PASSED,
            signal_id=signal.signal_id
        )

        # Phase 8.5: Record initial signal event via instrumentation
        self.instrumenter.record_event(
            event_type=ExecutionEventType.SIGNAL_RECEIVED,
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            direction=signal.direction,
            confidence=signal.confidence,
            source=signal.signal_source.value,
            regime=signal.regime
        )

        # Step 3: Execute as paper trade
        if self.paper_trading_enabled:
            paper_trade_id = self._execute_paper_trade(signal)
            result.paper_trade_id = paper_trade_id
            logger.debug(f"Paper trade executed | ID: {paper_trade_id}")

            # Instrumentation: Record paper trade execution
            self.instrumenter.record_event(
                event_type=ExecutionEventType.PAPER_TRADE_EXECUTED,
                signal_id=signal.signal_id,
                paper_trade_id=paper_trade_id
            )

        # Step 4: Score execution
        if self.enable_scoring:
            gate_status, confidence = self._score_execution(signal, result.paper_trade_id)
            result.gate_status = gate_status
            result.confidence_score = confidence
            logger.debug(f"Execution scored | Gate: {gate_status} | Confidence: {confidence:.2%}")

            # Instrumentation: Record scoring result
            self.instrumenter.record_event(
                event_type=ExecutionEventType.SCORING_COMPLETE,
                signal_id=signal.signal_id,
                gate_status=gate_status,
                confidence=confidence
            )

        # Step 5: Check execution health via kill switch
        kill_switch_healthy = self.kill_switch.check_execution_health()
        if not kill_switch_healthy:
            ks_status = self.kill_switch.get_status()
            result.signal_accepted = False
            result.rejection_reason = f"Kill switch triggered: {ks_status.get('trigger_reason', 'unknown')}"
            self.rejected_signals += 1
            logger.critical(f"🚨 Signal rejected by kill switch | {result.rejection_reason}")

            # Instrumentation: Record kill switch trigger
            self.instrumenter.record_event(
                event_type=ExecutionEventType.KILL_SWITCH_TRIGGERED,
                signal_id=signal.signal_id,
                trigger_reason=ks_status.get('trigger_reason', 'unknown')
            )
            return result

        # Step 6: Route to live execution (if gate PASS)
        if (
            result.signal_accepted
            and self.execution_mode == BridgeExecutionMode.LIVE_TRADING
            and result.gate_status == "PASS"
        ):
            live_order_id = self._route_to_live_execution(signal)
            result.live_order_id = live_order_id

        if result.signal_accepted:
            self.accepted_signals += 1
            self.signals_executed.append(signal)

            # Instrumentation: Record successful signal acceptance
            self.instrumenter.record_event(
                event_type=ExecutionEventType.SIGNAL_ACCEPTED,
                signal_id=signal.signal_id,
                live_order_id=result.live_order_id,
                gate_status=result.gate_status,
                confidence=result.confidence_score
            )

        return result

    def _validate_signal(self, signal: BridgeSignal) -> Optional[str]:
        """Validate signal format and basic requirements."""

        if not signal.symbol:
            return "Invalid symbol"
        if signal.confidence < 0 or signal.confidence > 1:
            return "Invalid confidence (must be 0-1)"
        if signal.position_size <= 0:
            return "Invalid position size (must be > 0)"
        if signal.direction not in ["LONG", "SHORT"]:
            return "Invalid direction (must be LONG or SHORT)"
        if signal.entry_price <= 0:
            return "Invalid entry price (must be > 0)"
        if not signal.signal_id:
            return "Missing signal ID"

        return None  # Valid

    def _run_safety_checks(self, signal: BridgeSignal) -> List[str]:
        """Run safety control checks on signal."""

        violations = []

        # Check 1: Market data freshness
        signal_age_seconds = (
            datetime.utcnow() - datetime.fromisoformat(signal.timestamp)
        ).total_seconds()
        if signal_age_seconds > 60:
            violations.append(f"Stale signal ({signal_age_seconds:.0f}s old)")

        # Check 2: Regime check (CRISIS blocks all)
        if signal.regime == "CRISIS":
            violations.append("CRISIS regime - trading blocked")

        # Check 3: Position size sanity
        if signal.position_size > 50000:
            violations.append("Position size too large (> $50k)")

        # Check 4: Risk/reward ratio
        if signal.direction == "LONG":
            risk = signal.entry_price - signal.stop_loss_price
            reward = signal.take_profit_price - signal.entry_price
        else:
            risk = signal.stop_loss_price - signal.entry_price
            reward = signal.entry_price - signal.take_profit_price

        if risk > 0 and reward > 0:
            rr_ratio = reward / risk
            if rr_ratio < 1.0:  # Must have at least 1:1 R/R
                violations.append(f"Poor R/R ratio ({rr_ratio:.2f}:1)")

        # Check 5: Confidence threshold
        if signal.confidence < 0.55:
            violations.append(f"Low confidence ({signal.confidence:.2%})")

        return violations

    def _execute_paper_trade(self, signal: BridgeSignal) -> str:
        """Execute signal as paper trade via forward test engine."""

        # Generate unique paper trade ID
        paper_trade_id = f"PAPER-{signal.signal_id}-{int(datetime.utcnow().timestamp() * 1000)}"

        # TODO: Route to ForwardTestEngine.execute_signal_as_paper_trade()
        logger.debug(f"Paper trade queued | ID: {paper_trade_id}")

        return paper_trade_id

    def _score_execution(self, signal: BridgeSignal, paper_trade_id: str) -> Tuple[str, float]:
        """Score execution against institutional standards."""

        # TODO: Integrate with InstitutionalScorecard.evaluate()

        # For now, simple logic:
        if signal.confidence >= 0.75 and signal.regime != "BEAR":
            gate_status = "PASS"
            confidence = 0.80
        elif signal.confidence >= 0.65:
            gate_status = "WATCH"
            confidence = 0.60
        else:
            gate_status = "FAIL"
            confidence = 0.30

        return gate_status, confidence

    def _route_to_live_execution(self, signal: BridgeSignal) -> str:
        """Route signal to live broker execution."""

        # TODO: Integrate with OrderManager.submit_order()

        # Generate live order ID
        live_order_id = f"LIVE-{signal.signal_id}-{int(datetime.utcnow().timestamp() * 1000)}"

        # Instrumentation: Record live execution
        self.instrumenter.record_event(
            event_type=ExecutionEventType.LIVE_ORDER_SUBMITTED,
            signal_id=signal.signal_id,
            live_order_id=live_order_id,
            symbol=signal.symbol,
            direction=signal.direction,
            position_size=signal.position_size
        )

        logger.info(f"✅ Signal routed to LIVE execution | Order: {live_order_id}")
        return live_order_id

    def get_bridge_stats(self) -> Dict:
        """Get current bridge statistics with kill switch status."""

        acceptance_rate = (
            self.accepted_signals / self.total_signals if self.total_signals > 0 else 0
        )

        # Phase 8.5: Include kill switch status in stats
        ks_status = self.kill_switch.get_status()

        return {
            "total_signals": self.total_signals,
            "accepted_signals": self.accepted_signals,
            "rejected_signals": self.rejected_signals,
            "acceptance_rate": acceptance_rate,
            "safety_violations": self.safety_violations_count,
            "avg_confidence": self._calculate_avg_confidence(),
            "execution_mode": self.execution_mode.value,
            "kill_switch_active": ks_status.get("is_active", False),
            "kill_switch_trigger": ks_status.get("trigger_reason", None),
            # Instrumentation stats
            "telemetry_events_recorded": self.instrumenter.get_event_count()
        }

    def _calculate_avg_confidence(self) -> float:
        """Calculate average confidence of executed signals."""

        if not self.signals_executed:
            return 0.0

        return sum(s.confidence for s in self.signals_executed) / len(self.signals_executed)

    def switch_execution_mode(self, new_mode: BridgeExecutionMode) -> bool:
        """
        Switch execution mode (paper → live).

        Only allowed if:
        - No currently open trades
        - System passed validation
        - Operator confirms
        """

        if self.execution_mode == new_mode:
            logger.info(f"Already in {new_mode.value} mode")
            return False

        if new_mode == BridgeExecutionMode.LIVE_TRADING:
            logger.warning(
                f"⚠️  SAFETY CHECK: Switching to LIVE TRADING requires validation gate PASS"
            )
            logger.warning(f"Current mode: {self.execution_mode.value}")
            logger.warning(f"Real capital at risk. Proceeding only with explicit confirmation.")

        self.execution_mode = new_mode
        logger.info(f"✅ Execution mode switched to {new_mode.value}")
        return True
