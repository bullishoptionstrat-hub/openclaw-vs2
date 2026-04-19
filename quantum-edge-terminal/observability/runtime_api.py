"""
TELEMETRY INITIALIZATION & RUNTIME API
======================================

Provides the public interface for initializing and using OpenTelemetry
instrumentation in the quantum-edge-terminal trading system.

This is the entry point that applications and plugins call to enable
observability features for their execution pipelines.

Usage:
    from observability.runtime_api import initialize_telemetry, get_tracer

    # At application startup
    config = TelemetryConfig(environment="production")
    initialize_telemetry(config)

    # During execution
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("process_signal"):
        # ... process signal
        pass
"""

import logging
import atexit
from typing import Optional

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

from .telemetry_config import TelemetryConfig, ExportProtocol
from .execution_instrumenter import ExecutionInstrumenter

logger = logging.getLogger(__name__)

# Global state
_initialized = False
_tracer_provider: Optional[TracerProvider] = None
_span_processor = None
_execution_instrumenter: Optional[ExecutionInstrumenter] = None


def initialize_telemetry(config: TelemetryConfig) -> bool:
    """
    Initialize OpenTelemetry SDK with specified configuration.

    This function should be called once at application startup, before
    any trades or signals are processed.

    Args:
        config: TelemetryConfig instance with backend settings

    Returns:
        True if initialization successful, False otherwise

    Example:
        config = TelemetryConfig(
            export_protocol=ExportProtocol.OTLP_GRPC,
            otlp_endpoint="http://localhost:4317",
            service_name="quantum-edge-terminal",
        )
        success = initialize_telemetry(config)
        if not success:
            logger.error("Failed to initialize telemetry")
            sys.exit(1)
    """
    global _initialized, _tracer_provider, _span_processor, _execution_instrumenter

    if _initialized:
        logger.warning("Telemetry already initialized, skipping")
        return True

    try:
        # Validate configuration
        valid, errors = config.validate()
        if not valid:
            logger.error(f"Invalid telemetry configuration: {errors}")
            return False

        # Create resource with service metadata
        resource = Resource.create(
            {
                "service.name": config.service_name,
                "service.version": config.service_version,
                "deployment.environment": config.environment,
            }
        )

        # Set up span exporter based on protocol
        span_exporter = None

        if config.export_protocol == ExportProtocol.OTLP_GRPC:
            logger.info(f"Initializing OTLP exporter to {config.otlp_endpoint}")
            span_exporter = OTLPSpanExporter(
                endpoint=config.otlp_endpoint,
                timeout=config.otlp_timeout_ms,
            )

        elif config.export_protocol == ExportProtocol.JAEGER:
            logger.info(
                f"Initializing Jaeger exporter to {config.jaeger_host}:{config.jaeger_port}"
            )
            span_exporter = JaegerExporter(
                agent_host_name=config.jaeger_host,
                agent_port=config.jaeger_port,
                max_tag_value_length=256,
            )

        elif config.export_protocol == ExportProtocol.CONSOLE:
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor

            logger.info("Initializing console exporter (debug mode)")
            # Will use SimpleSpanProcessor for immediate output
            span_exporter = None  # Use debug exporter

        else:
            logger.info(f"No exporter configured: {config.export_protocol}")
            span_exporter = None

        # Create TracerProvider with resource
        _tracer_provider = TracerProvider(resource=resource)

        # Add span processor
        if span_exporter:
            _span_processor = BatchSpanProcessor(
                span_exporter,
                schedule_delay_millis=config.export_interval_ms,
            )
            _tracer_provider.add_span_processor(_span_processor)

        # Set as global provider
        trace.set_tracer_provider(_tracer_provider)

        # Initialize ExecutionInstrumenter
        _execution_instrumenter = ExecutionInstrumenter()
        logger.info(
            f"ExecutionInstrumenter initialized (event buffer size: unlimited, auto-flush support)"
        )

        # Register shutdown hook
        atexit.register(_shutdown_telemetry)

        _initialized = True
        logger.info(
            f"✅ Telemetry initialized: "
            f"service={config.service_name}, "
            f"env={config.environment}, "
            f"protocol={config.export_protocol.value}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to initialize telemetry: {e}", exc_info=True)
        return False


def get_tracer(name: str, version: str = None):
    """
    Get a tracer instance for creating spans.

    Args:
        name: Name of the tracer (typically __name__)
        version: Optional version of the module

    Returns:
        Tracer instance for creating spans

    Example:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("process_order") as span:
            span.set_attribute("order.id", order_id)
            # ... process order
    """
    if not _initialized:
        logger.warning("Telemetry not initialized, using noop tracer")
        return trace.get_tracer(__name__)

    return _tracer_provider.get_tracer(name, version=version)


def get_execution_instrumenter() -> Optional[ExecutionInstrumenter]:
    """
    Get the global ExecutionInstrumenter instance.

    Returns:
        ExecutionInstrumenter or None if not initialized

    Example:
        instrumenter = get_execution_instrumenter()
        if instrumenter:
            count = instrumenter.get_event_count()
            events_json = instrumenter.export_events_json()
    """
    if not _initialized:
        logger.warning("Telemetry not initialized")
        return None

    return _execution_instrumenter


def record_event(event_type, attributes: dict = None):
    """
    Record an execution event through the ExecutionInstrumenter.

    Args:
        event_type: ExecutionEventType enum value
        attributes: Optional dict of event attributes

    Example:
        from observability.execution_instrumenter import ExecutionEventType

        record_event(
            ExecutionEventType.SIGNAL_RECEIVED,
            {"signal_id": "sig_123", "symbol": "BTC"}
        )
    """
    if _execution_instrumenter:
        _execution_instrumenter.record_event(event_type, attributes or {})
    else:
        logger.debug(f"Event recorded (no instrumenter): {event_type}")


def export_telemetry():
    """
    Force export of all recorded telemetry.

    This is useful for:
    - Flushing before shutdown
    - Periodic checkpoints
    - Testing and debugging

    Returns:
        exported_json: JSON representation of exported data
    """
    if not _execution_instrumenter:
        logger.warning("No instrumentation to export")
        return None

    exported = _execution_instrumenter.export_events_json()
    logger.info(f"✅ Exported telemetry: {len(exported)} bytes")
    return exported


def get_telemetry_stats():
    """
    Get current telemetry statistics.

    Returns:
        dict with event counts, timings, etc.
    """
    if not _execution_instrumenter:
        return None

    return {
        "total_events": _execution_instrumenter.get_event_count(),
        "events_by_type": {
            str(k): v for k, v in _execution_instrumenter.get_events_by_type().items()
        },
        "initialized": _initialized,
    }


def _shutdown_telemetry():
    """
    Shutdown hook: flush and close telemetry resources.
    Called automatically at program exit.
    """
    global _span_processor

    logger.info("Shutting down telemetry...")

    try:
        # Export final events
        if _execution_instrumenter:
            export_telemetry()

        # Flush spans
        if _tracer_provider:
            _tracer_provider.force_flush(timeout_millis=5000)

        # Close exporter
        if _span_processor:
            _span_processor.shutdown()

        logger.info("✅ Telemetry shutdown complete")

    except Exception as e:
        logger.error(f"Error during telemetry shutdown: {e}", exc_info=True)


# Module-level convenience functions


def initialize_defaults():
    """Initialize telemetry with default dev configuration."""
    from .telemetry_config import CONFIG_DEV

    return initialize_telemetry(CONFIG_DEV)


def initialize_production(otlp_endpoint: str = None):
    """Initialize telemetry with production defaults."""
    from .telemetry_config import CONFIG_PRODUCTION

    config = CONFIG_PRODUCTION
    if otlp_endpoint:
        config.otlp_endpoint = otlp_endpoint
    return initialize_telemetry(config)
