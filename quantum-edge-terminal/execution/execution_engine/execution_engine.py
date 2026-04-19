"""
EXECUTION ENGINE - TRADE VALIDATION & EXECUTION PAYLOAD GENERATION

Converts AI-generated trade signals into execution-ready payloads.

Flow:
1. Validate incoming trade (structure, required fields)
2. Fetch current macro regime
3. Apply macro filter (hard gates + position sizing)
4. Calculate final position size
5. Generate execution payload with tracking metadata
6. Return to caller (alert engine, websocket, trade journal)

Key Principle:
- DO NOT auto-execute. Generate ready-to-execute payloads.
- All trades MUST pass macro filter before execution.
- Position sizing is deterministic (regime × confidence).
- Every trade gets unique ID + timestamp for tracking.
"""

import uuid
import logging
from datetime import datetime
from dataclasses import dataclass, asdict, field
from typing import Dict, Optional, List, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """Trade execution status."""

    PENDING = "pending"  # Ready for manual confirmation or auto-execution
    VALIDATION_FAILED = "validation_failed"  # Failed macro filter
    EXECUTED = "executed"  # Successfully sent to exchange/broker
    PARTIAL = "partial"  # Partially filled
    FILLED = "filled"  # Full execution at entry
    ACTIVE = "active"  # Waiting for TP/SL
    TP_HIT = "tp_hit"  # Take profit triggered
    SL_HIT = "sl_hit"  # Stop loss triggered
    CLOSED = "closed"  # Trade closed manually
    CANCELLED = "cancelled"  # Trade cancelled before execution


@dataclass
class ExecutionPayload:
    """
    Execution-ready trade payload.

    This object is the contract between:
    - Execution engine (creates it)
    - Alert engine (sends notifications)
    - Trade journal (tracks it)
    - WebSocket stream (broadcasts it)
    """

    # Core trade identification
    trade_id: str  # Unique UUID for this trade
    asset: str  # ES, NQ, GC, etc
    direction: str  # LONG or SHORT
    timestamp: str  # ISO 8601 creation timestamp

    # Trade structure
    entry: float  # Entry price
    stop_loss: float  # Stop loss price
    take_profit_targets: List[float] = field(default_factory=list)  # Multiple TP levels

    # Position sizing
    position_size: float  # Number of contracts / shares
    risk_amount: float  # Dollar risk (entry - stop)
    reward_amount: float  # Dollar reward (TP - entry)
    risk_reward_ratio: float  # reward / risk

    # Signal confidence & macro context
    signal_confidence: float  # 0.0-1.0 from AI engine
    signal_type: str  # "breakout", "mean_reversion", "momentum", etc
    macro_regime: str  # Current regime (STRONG_RISK_ON, RISK_ON, etc)
    macro_score: float  # -5 to +5
    macro_confidence: float  # 0.0-1.0

    # Execution metadata
    status: ExecutionStatus = field(default=ExecutionStatus.PENDING)
    macro_validated: bool = False  # Passed macro filter check
    position_size_multiplier: float = 1.0  # From macro filter (0.0-1.5x)

    # Additional context
    confluence_score: Optional[float] = None  # Confluence of multiple signals
    active_alerts: List[str] = field(default_factory=list)  # Alert tiers triggered (Tier1/2/3)
    notes: str = ""  # Additional trade notes

    # Tracking
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    executed_at: Optional[str] = None
    filled_at: Optional[str] = None
    closed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API/JSON serialization."""
        d = asdict(self)
        d["status"] = self.status.value
        return d

    def alert_payload(self) -> Dict[str, Any]:
        """Generate alert-specific payload."""
        return {
            "trade_id": self.trade_id,
            "asset": self.asset,
            "direction": self.direction,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit_targets[0] if self.take_profit_targets else None,
            "size": self.position_size,
            "confidence": self.signal_confidence,
            "macro_regime": self.macro_regime,
            "signal_type": self.signal_type,
            "confluence_score": self.confluence_score,
            "timestamp": self.timestamp,
        }

    def dashboard_payload(self) -> Dict[str, Any]:
        """Generate dashboard display payload."""
        return {
            "trade_id": self.trade_id,
            "asset": self.asset,
            "direction": self.direction,
            "entry": self.entry,
            "stop": self.stop_loss,
            "tp": self.take_profit_targets,
            "size": self.position_size,
            "rr": self.risk_reward_ratio,
            "signal_conf": self.signal_confidence,
            "signal_type": self.signal_type,
            "macro": self.macro_regime,
            "status": self.status.value,
            "timestamp": self.timestamp,
        }


@dataclass
class ExecutionValidationResult:
    """Result of trade validation."""

    valid: bool
    trade: Optional[ExecutionPayload] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "valid": self.valid,
            "trade": self.trade.to_dict() if self.trade else None,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class ExecutionEngine:
    """
    Core execution engine.

    Validates trades and generates execution payloads.
    """

    def __init__(
        self,
        macro_filter_func=None,
        classify_regime_func=None,
        base_position_size: float = 1.0,
    ):
        """
        Initialize execution engine.

        Args:
            macro_filter_func: Function to filter trades by macro regime
            classify_regime_func: Function to get current macro regime
            base_position_size: Base unit size (1 contract, 1 share, etc)
        """
        self.macro_filter = macro_filter_func
        self.classify_regime = classify_regime_func
        self.base_position_size = base_position_size
        self.executed_trades = {}  # Dict[trade_id, ExecutionPayload]

    def create_execution(
        self,
        signal: Dict,
        macro_features: Dict,
    ) -> ExecutionValidationResult:
        """
        Create execution payload from AI signal.

        Args:
            signal: {
                "asset": str,
                "direction": str,  # LONG or SHORT
                "entry": float,
                "stop_loss": float,
                "take_profit_targets": List[float],
                "confidence": float,  # 0.0-1.0
                "signal_type": str,
                "confluence_score": float (optional),
                "notes": str (optional)
            }
            macro_features: Features dict for regime classification

        Returns:
            ExecutionValidationResult with ExecutionPayload if valid
        """

        errors = []
        warnings = []

        # ========== VALIDATE INPUT ==========

        required_fields = ["asset", "direction", "entry", "stop_loss"]
        for field in required_fields:
            if field not in signal:
                errors.append(f"Missing required field: {field}")

        if "confidence" not in signal or not (0.0 <= signal["confidence"] <= 1.0):
            errors.append("Signal confidence must be 0.0-1.0")

        if signal.get("direction", "").upper() not in ["LONG", "SHORT"]:
            errors.append("Direction must be LONG or SHORT")

        # Validate price structure
        entry = signal.get("entry", 0)
        stop = signal.get("stop_loss", 0)
        targets = signal.get("take_profit_targets", [])

        if signal.get("direction", "").upper() == "LONG":
            if stop >= entry:
                errors.append(f"LONG: stop loss ({stop}) must be below entry ({entry})")
            if not all(t > entry for t in targets):
                errors.append(f"LONG: all targets must be above entry ({entry})")
        else:  # SHORT
            if stop <= entry:
                errors.append(f"SHORT: stop loss ({stop}) must be above entry ({entry})")
            if not all(t < entry for t in targets):
                errors.append(f"SHORT: all targets must be below entry ({entry})")

        if errors:
            return ExecutionValidationResult(valid=False, errors=errors)

        # ========== FETCH MACRO REGIME ==========

        try:
            if self.classify_regime:
                regime_dict = self.classify_regime(macro_features)
                macro_regime = regime_dict.get("regime", "NEUTRAL")
                macro_score = regime_dict.get("score", 0.0)
                macro_confidence = regime_dict.get("confidence", 0.5)
            else:
                macro_regime = "NEUTRAL"
                macro_score = 0.0
                macro_confidence = 0.5
        except Exception as e:
            warnings.append(f"Could not classify macro regime: {str(e)}")
            macro_regime = "NEUTRAL"
            macro_score = 0.0
            macro_confidence = 0.5

        # ========== APPLY MACRO FILTER ==========

        position_size_multiplier = 1.0
        macro_validated = True

        if self.macro_filter:
            try:
                trade_for_filter = {
                    "direction": signal.get("direction"),
                    "confidence": signal.get("confidence"),
                    "signal_type": signal.get("signal_type", "unknown"),
                }

                # Create a minimal RegimeState for filter
                # (assumes macro_filter expects RegimeState or dict)
                regime_state = {
                    "regime": macro_regime,
                    "score": macro_score,
                    "confidence": macro_confidence,
                }

                filter_result = self.macro_filter(trade_for_filter, regime_state)

                # Handle both MacroFilterResult object and dict
                if hasattr(filter_result, "decision"):
                    decision = filter_result.decision.value
                    position_size_multiplier = filter_result.position_size_multiplier
                    if decision == "reject":
                        macro_validated = False
                        errors.append(f"Macro filter rejected: {filter_result.reason}")
                else:
                    decision = filter_result.get("decision", "accept")
                    position_size_multiplier = filter_result.get("position_size_multiplier", 1.0)
                    if decision == "reject":
                        macro_validated = False
                        errors.append(f"Macro filter rejected trade")

            except Exception as e:
                warnings.append(f"Macro filter error: {str(e)}")

        # ========== CALCULATE POSITION SIZE ==========

        base_size = self.base_position_size
        signal_confidence = signal.get("confidence", 0.5)

        # Position size = base × macro_multiplier × confidence_bonus
        final_position_size = base_size * position_size_multiplier

        # Add confidence bonus (high confidence = larger position in favorable regimes)
        if signal_confidence > 0.75 and macro_regime in ["RISK_ON", "STRONG_RISK_ON"]:
            confidence_bonus = min(0.2, (signal_confidence - 0.75) * 0.4)
            final_position_size *= 1 + confidence_bonus

        # ========== CALCULATE RISK / REWARD ==========

        entry = signal.get("entry")
        stop = signal.get("stop_loss")
        targets = signal.get("take_profit_targets", [])

        risk_amount = abs(entry - stop)
        reward_amount = abs(targets[0] - entry) if targets else 0
        risk_reward_ratio = reward_amount / risk_amount if risk_amount > 0 else 0

        # ========== CREATE EXECUTION PAYLOAD ==========

        execution_payload = ExecutionPayload(
            trade_id=str(uuid.uuid4()),
            asset=signal.get("asset"),
            direction=signal.get("direction").upper(),
            timestamp=datetime.utcnow().isoformat(),
            entry=entry,
            stop_loss=stop,
            take_profit_targets=targets,
            position_size=final_position_size,
            risk_amount=risk_amount,
            reward_amount=reward_amount,
            risk_reward_ratio=risk_reward_ratio,
            signal_confidence=signal_confidence,
            signal_type=signal.get("signal_type", "unknown"),
            macro_regime=macro_regime,
            macro_score=macro_score,
            macro_confidence=macro_confidence,
            status=ExecutionStatus.PENDING
            if macro_validated
            else ExecutionStatus.VALIDATION_FAILED,
            macro_validated=macro_validated,
            position_size_multiplier=position_size_multiplier,
            confluence_score=signal.get("confluence_score"),
            notes=signal.get("notes", ""),
        )

        # Store in registry
        self.executed_trades[execution_payload.trade_id] = execution_payload

        logger.info(
            f"Execution created: {execution_payload.trade_id} | "
            f"{execution_payload.asset} {execution_payload.direction} | "
            f"Size: {execution_payload.position_size:.2f} | "
            f"Status: {execution_payload.status.value}"
        )

        return ExecutionValidationResult(
            valid=macro_validated,
            trade=execution_payload,
            errors=errors,
            warnings=warnings,
        )

    def get_trade(self, trade_id: str) -> Optional[ExecutionPayload]:
        """Retrieve execution payload by trade ID."""
        return self.executed_trades.get(trade_id)

    def update_trade_status(self, trade_id: str, status: ExecutionStatus) -> bool:
        """Update trade status (e.g., PENDING → EXECUTED)."""
        if trade_id in self.executed_trades:
            trade = self.executed_trades[trade_id]
            trade.status = status
            if status == ExecutionStatus.EXECUTED:
                trade.executed_at = datetime.utcnow().isoformat()
            elif status == ExecutionStatus.FILLED:
                trade.filled_at = datetime.utcnow().isoformat()
            elif status in [
                ExecutionStatus.CLOSED,
                ExecutionStatus.TP_HIT,
                ExecutionStatus.SL_HIT,
            ]:
                trade.closed_at = datetime.utcnow().isoformat()
            return True
        return False

    def list_active_trades(self) -> List[ExecutionPayload]:
        """Get all active trades."""
        return [
            t
            for t in self.executed_trades.values()
            if t.status in [ExecutionStatus.PENDING, ExecutionStatus.ACTIVE]
        ]

    def list_trades_by_status(self, status: ExecutionStatus) -> List[ExecutionPayload]:
        """Get trades by status."""
        return [t for t in self.executed_trades.values() if t.status == status]
