"""
EXECUTION INSTRUMENTATION - OPENTELEMETRY SPANS AND METRICS

Adds comprehensive tracing and metrics to trading execution paths.

Spans track:
- Order submission lifecycle
- Execution quality assessment
- Signal processing
- Capital deployment decisions

Metrics track:
- Execution count by symbol
- Fill rates
- Slippage distribution
- Order latency
- Kill switch triggers
"""

import logging
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
import json

from opentelemetry import trace, metrics
from opentelemetry.trace import Tracer, Status, StatusCode
from opentelemetry.metrics import Meter

logger = logging.getLogger(__name__)


class ExecutionEventType(Enum):
    """Types of execution events to trace."""

    # Signal processing events
    SIGNAL_GENERATED = "signal_generated"
    SIGNAL_RECEIVED = "signal_received"
    SIGNAL_ACCEPTED = "signal_accepted"
    SIGNAL_REJECTED = "signal_rejected"

    # Validation events
    VALIDATION_FAILED = "validation_failed"
    SAFETY_CHECKS_PASSED = "safety_checks_passed"
    SAFETY_VIOLATION = "safety_violation"

    # Order execution events
    ORDER_CREATED = "order_created"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_ACKED = "order_acked"
    ORDER_FILLED = "order_filled"
    ORDER_REJECTED = "order_rejected"
    ORDER_CANCELED = "order_canceled"

    # Paper/Live execution events
    PAPER_TRADE_EXECUTED = "paper_trade_executed"
    LIVE_ORDER_SUBMITTED = "live_order_submitted"

    # Scoring and gating events
    SCORING_COMPLETE = "scoring_complete"
    GATE_DECISION = "gate_decision"
    EVALUATION_DEFERRED = "evaluation_deferred"

    # Lifecycle events
    PHASE_TRANSITION = "phase_transition"
    STAGE_ADVANCED = "stage_advanced"
    EXECUTION_COMPLETE = "execution_complete"
    KILL_SWITCH_TRIGGERED = "kill_switch_triggered"

    # Error events
    VALIDATION_ERROR = "validation_error"


class ExecutionInstrumenter:
    """
    Instrument trading execution with OpenTelemetry traces and metrics.

    Provides context managers and decorators for automatically creating
    spans around execution operations.
    """

    def __init__(self, tracer: Optional[Tracer] = None, meter: Optional[Meter] = None):
        """
        Initialize instrumenter.

        Args:
            tracer: OpenTelemetry Tracer (gets global if None)
            meter: OpenTelemetry Meter (gets global if None)
        """

        self.tracer = tracer or trace.get_tracer(__name__)
        self.meter = meter or metrics.get_meter(__name__)

        # Event tracking for testing/verification
        self.events: List[Dict[str, Any]] = []

        # Create metrics
        self._init_metrics()

        logger.info("ExecutionInstrumenter initialized")

    def _init_metrics(self) -> None:
        """Initialize metrics."""

        # Counter: Total executions by symbol
        self.execution_counter = self.meter.create_counter(
            name="execution.submitted",
            description="Number of order submissions",
            unit="{orders}",
        )

        # Counter: Orders filled
        self.filled_counter = self.meter.create_counter(
            name="execution.filled",
            description="Number of orders filled",
            unit="{orders}",
        )

        # Counter: Orders rejected
        self.rejected_counter = self.meter.create_counter(
            name="execution.rejected",
            description="Number of orders rejected",
            unit="{orders}",
        )

        # Histogram: Fill latency
        self.fill_latency_histogram = self.meter.create_histogram(
            name="execution.fill_latency_ms",
            description="Time from signal to fill in milliseconds",
            unit="ms",
        )

        # Histogram: Slippage
        self.slippage_histogram = self.meter.create_histogram(
            name="execution.slippage_bps",
            description="Slippage in basis points",
            unit="bps",
        )

        # Counter: Kill switch triggers
        self.kill_switch_counter = self.meter.create_counter(
            name="execution.kill_switch_triggered",
            description="Number of kill switch triggers",
            unit="{triggers}",
        )

        # Gauge: Current fill rate
        self.fill_rate_gauge = self.meter.create_gauge(
            name="execution.fill_rate",
            description="Current fill rate percentage",
            unit="%",
        )

        # Counter: Capital deployed
        self.capital_deployed_counter = self.meter.create_counter(
            name="deployment.capital_deployed",
            description="Amount of capital deployed",
            unit="USD",
        )

        logger.info("Metrics initialized")

    @contextmanager
    def trace_signal_processing(self, symbol: str, direction: str, confidence: float):
        """
        Trace signal processing operation.

        Context manager that creates span for entire signal processing.

        Args:
            symbol: Trading symbol
            direction: LONG or SHORT
            confidence: Signal confidence (0-1)

        Usage:
            with instrumenter.trace_signal_processing("AAPL", "LONG", 0.75):
                # Process signal
                pass
        """

        with self.tracer.start_as_current_span("signal_processing") as span:
            span.set_attribute("symbol", symbol)
            span.set_attribute("direction", direction)
            span.set_attribute("confidence", confidence)
            span.set_attribute("timestamp", datetime.utcnow().isoformat())

            try:
                yield span
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    @contextmanager
    def trace_order_submission(
        self, symbol: str, qty: int, side: str, order_type: str, order_id: Optional[str] = None
    ):
        """
        Trace order submission lifecycle.

        Context manager for complete order submission and fill process.

        Args:
            symbol: Trading symbol
            qty: Quantity
            side: buy or sell
            order_type: market, limit, bracket
            order_id: Broker order ID (optional, set after submission)

        Usage:
            with instrumenter.trace_order_submission("AAPL", 100, "buy", "market") as span:
                # Submit order
                order_status = broker.submit_order(...)
                span.set_attribute("order_id", order_status.order_id)
                # Wait for fills
                pass
        """

        with self.tracer.start_as_current_span("order_submission") as span:
            span.set_attribute("symbol", symbol)
            span.set_attribute("quantity", qty)
            span.set_attribute("side", side)
            span.set_attribute("order_type", order_type)
            span.set_attribute("submit_time", datetime.utcnow().isoformat())

            self.execution_counter.add(1, {"symbol": symbol, "side": side, "order_type": order_type})

            try:
                yield span
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    @contextmanager
    def trace_order_fill(
        self,
        symbol: str,
        filled_qty: int,
        fill_price: float,
        expected_price: float,
        fill_latency_ms: float,
    ):
        """
        Trace order fill event.

        Args:
            symbol: Trading symbol
            filled_qty: Quantity filled
            fill_price: Actual fill price
            expected_price: Expected fill price (for slippage)
            fill_latency_ms: Time from signal to fill in ms
        """

        slippage_bps = ((fill_price - expected_price) / expected_price * 10000) if expected_price > 0 else 0

        with self.tracer.start_as_current_span("order_filled") as span:
            span.set_attribute("symbol", symbol)
            span.set_attribute("filled_qty", filled_qty)
            span.set_attribute("fill_price", fill_price)
            span.set_attribute("expected_price", expected_price)
            span.set_attribute("slippage_bps", slippage_bps)
            span.set_attribute("fill_latency_ms", fill_latency_ms)
            span.set_attribute("fill_time", datetime.utcnow().isoformat())

            self.filled_counter.add(1, {"symbol": symbol})
            self.fill_latency_histogram.record(fill_latency_ms, {"symbol": symbol})
            self.slippage_histogram.record(slippage_bps, {"symbol": symbol})

            span.set_status(Status(StatusCode.OK))
            yield span

    @contextmanager
    def trace_order_rejection(self, symbol: str, qty: int, rejection_reason: str):
        """
        Trace order rejection event.

        Args:
            symbol: Trading symbol
            qty: Quantity attempted
            rejection_reason: Why order was rejected
        """

        with self.tracer.start_as_current_span("order_rejected") as span:
            span.set_attribute("symbol", symbol)
            span.set_attribute("quantity", qty)
            span.set_attribute("rejection_reason", rejection_reason)
            span.set_attribute("rejection_time", datetime.utcnow().isoformat())

            self.rejected_counter.add(1, {"symbol": symbol, "reason": rejection_reason})
            span.set_status(Status(StatusCode.ERROR, rejection_reason))

            yield span

    @contextmanager
    def trace_execution_validation(self, metrics: Dict[str, Any]):
        """
        Trace execution quality validation.

        Args:
            metrics: Execution metrics (fill_rate, slippage, etc.)
        """

        with self.tracer.start_as_current_span("execution_validation") as span:
            for key, value in metrics.items():
                if isinstance(value, (int, float, str, bool)):
                    span.set_attribute(f"metric.{key}", value)

            try:
                yield span
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    @contextmanager
    def trace_kill_switch_check(self, current_metrics: Dict[str, Any]):
        """
        Trace kill switch health check.

        Args:
            current_metrics: Current execution metrics
        """

        with self.tracer.start_as_current_span("kill_switch_check") as span:
            for key, value in current_metrics.items():
                if isinstance(value, (int, float, str, bool)):
                    span.set_attribute(f"metric.{key}", value)

            try:
                yield span
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                # Kill switch triggered
                span.set_attribute("triggered", True)
                span.set_attribute("trigger_reason", str(e))
                self.kill_switch_counter.add(1, {"reason": str(e)})
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise

    @contextmanager
    def trace_stage_advancement(
        self, current_stage: str, next_stage: str, operator: str, metrics: Dict[str, Any]
    ):
        """
        Trace deployment stage advancement.

        Args:
            current_stage: Current deployment stage
            next_stage: Target deployment stage
            operator: Operator name approving advance
            metrics: Gate evaluation metrics
        """

        with self.tracer.start_as_current_span("stage_advancement") as span:
            span.set_attribute("current_stage", current_stage)
            span.set_attribute("next_stage", next_stage)
            span.set_attribute("operator", operator)
            span.set_attribute("advancement_time", datetime.utcnow().isoformat())

            for key, value in metrics.items():
                if isinstance(value, (int, float, str, bool)):
                    span.set_attribute(f"gate.{key}", value)

            try:
                self.capital_deployed_counter.add(1, {"stage": next_stage})
                yield span
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    def record_event(self, event_type: ExecutionEventType, attributes: Dict[str, Any] = None):
        """
        Record execution event.

        Args:
            event_type: Type of event
            attributes: Event attributes
        """

        attributes = attributes or {}
        attributes["event_type"] = event_type.value
        attributes["timestamp"] = datetime.utcnow().isoformat()

        # Add to event log for testing/verification
        self.events.append(attributes)

        with self.tracer.start_as_current_span(f"event.{event_type.value}") as span:
            for key, value in attributes.items():
                if isinstance(value, (int, float, str, bool)):
                    span.set_attribute(key, value)
            span.set_status(Status(StatusCode.OK))

        logger.debug(f"Event recorded: {event_type.value} | {attributes}")

    def get_event_count(self) -> int:
        """Get total number of events recorded."""
        return len(self.events)

    def get_events_by_type(self, event_type: ExecutionEventType) -> List[Dict[str, Any]]:
        """
        Get all events of a specific type.

        Args:
            event_type: Type of event to filter by

        Returns:
            List of events matching the type
        """
        return [e for e in self.events if e.get("event_type") == event_type.value]

    def export_events_json(self) -> str:
        """
        Export all recorded events as JSON string.

        Returns:
            JSON string containing all events
        """
        return json.dumps({"events": self.events}, indent=2)

    def clear_events(self) -> None:
        """Clear all recorded events."""
        self.events = []

    def update_fill_rate_metric(self, fill_rate: float):
        """Update current fill rate metric."""
        self.fill_rate_gauge.observe(fill_rate * 100)

    def add_custom_metric(self, name: str, value: float, unit: str = "1", attributes: Dict = None):
        """
        Add custom metric (counter or gauge).

        Args:
            name: Metric name
            value: Metric value
            unit: Unit of measurement
            attributes: Metric attributes
        """

        attributes = attributes or {}

        # Creating counter for each metric for simplicity
        counter = self.meter.create_counter(name=name, unit=unit)
        counter.add(value, attributes)

        logger.debug(f"Custom metric recorded: {name}={value}{unit}")
