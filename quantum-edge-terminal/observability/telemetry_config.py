"""
OPENTELEMETRY SDK CONFIGURATION

Complete observability setup for quantum-edge-terminal trading system.

Responsibilities:
1. Initialize TracerProvider and MeterProvider
2. Configure trace and metric exporters (OTLP, Console, File)
3. Set up instrumentation libraries
4. Manage SDK lifecycle
5. Export telemetry data

Docs: https://opentelemetry.io/docs/languages/sdk-configuration/
"""

import logging
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# OpenTelemetry imports
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased, ProbabilitySampler
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

logger = logging.getLogger(__name__)


class ExportProtocol(Enum):
    """Trace and metric export protocols."""

    OTLP_GRPC = "otlp_grpc"  # OpenTelemetry Protocol over gRPC
    JAEGER = "jaeger"  # Jaeger thrift protocol
    CONSOLE = "console"  # Console printing (debug)
    NONE = "none"  # No export


class SamplingStrategy(Enum):
    """Trace sampling strategies."""

    ALWAYS_ON = "always_on"  # Sample everything
    ALWAYS_OFF = "always_off"  # Sample nothing
    PROBABILITY = "probability"  # Sample by probability
    ADAPTIVE = "adaptive"  # Sample based on load


@dataclass
class TelemetryConfig:
    """OpenTelemetry SDK configuration."""

    # Service identification
    service_name: str = "quantum-edge-terminal"
    service_version: str = "8.5.0"
    environment: str = "production"  # dev, staging, production

    # Export configuration
    export_protocol: ExportProtocol = ExportProtocol.OTLP_GRPC
    export_enabled: bool = True
    export_interval_ms: int = 5000  # 5 seconds

    # OTLP configuration
    otlp_endpoint: str = "localhost:4317"  # OTLP gRPC endpoint
    otlp_timeout_ms: int = 10000  # 10 seconds

    # Jaeger configuration
    jaeger_host: str = "localhost"
    jaeger_port: int = 6831
    jaeger_timeout_ms: int = 10000

    # Sampling configuration
    sampling_strategy: SamplingStrategy = SamplingStrategy.PROBABILITY
    sampling_probability: float = 0.1  # Sample 10% of traces

    # Resource attributes
    additional_attributes: Dict[str, Any] = None

    # Feature flags
    enable_logging_instrumentation: bool = True
    enable_requests_instrumentation: bool = True
    enable_metrics: bool = True
    enable_traces: bool = True
    enable_debug_exporter: bool = False

    def __post_init__(self):
        """Validate configuration."""
        if self.sampling_probability < 0 or self.sampling_probability > 1:
            raise ValueError("sampling_probability must be between 0 and 1")

        if self.export_protocol == ExportProtocol.NONE:
            logger.warning("OpenTelemetry export disabled - no observability data will be collected")

        if self.additional_attributes is None:
            self.additional_attributes = {}


class TelemetrySDK:
    """
    OpenTelemetry SDK manager.

    Provides complete initialization and lifecycle management for
    traces, metrics, and logs collection.
    """

    def __init__(self, config: TelemetryConfig):
        """
        Initialize OpenTelemetry SDK.

        Args:
            config: TelemetryConfig with all settings
        """

        self.config = config
        self.tracer_provider: Optional[TracerProvider] = None
        self.meter_provider: Optional[MeterProvider] = None
        self.tracer: Optional[trace.Tracer] = None
        self.meter: Optional[metrics.Meter] = None

        logger.info(
            f"TelemetrySDK initializing | "
            f"Service: {config.service_name} v{config.service_version} | "
            f"Environment: {config.environment} | "
            f"Protocol: {config.export_protocol.value}"
        )

    def initialize(self) -> bool:
        """
        Initialize OpenTelemetry SDK.

        Sets up:
        - Resource attributes
        - TracerProvider with configured sampling
        - MeterProvider with exporters
        - Instrumentation libraries

        Returns:
            True if initialization successful
        """

        try:
            # Create resource with service attributes
            resource = self._create_resource()

            # Initialize traces
            if self.config.enable_traces:
                self.tracer_provider = self._init_tracer_provider(resource)
                trace.set_tracer_provider(self.tracer_provider)
                self.tracer = self.tracer_provider.get_tracer(__name__)
                logger.info("✓ TracerProvider initialized")

            # Initialize metrics
            if self.config.enable_metrics:
                self.meter_provider = self._init_meter_provider(resource)
                metrics.set_meter_provider(self.meter_provider)
                self.meter = self.meter_provider.get_meter(__name__)
                logger.info("✓ MeterProvider initialized")

            # Initialize instrumentation libraries
            self._init_instrumentations()

            logger.info("✅ OpenTelemetry SDK initialized successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize OpenTelemetry SDK: {e}")
            return False

    def _create_resource(self) -> Resource:
        """Create Resource with service attributes."""

        attributes = {
            "service.name": self.config.service_name,
            "service.version": self.config.service_version,
            "deployment.environment": self.config.environment,
        }

        # Add additional attributes
        if self.config.additional_attributes:
            attributes.update(self.config.additional_attributes)

        return Resource(attributes=attributes)

    def _init_tracer_provider(self, resource: Resource) -> TracerProvider:
        """Initialize TracerProvider with exporters."""

        # Add sampling strategy
        sampler = self._create_sampler()

        tracer_provider = TracerProvider(resource=resource, sampler=sampler)

        # Add trace exporters
        if self.config.export_protocol == ExportProtocol.OTLP_GRPC:
            span_exporter = OTLPSpanExporter(
                endpoint=self.config.otlp_endpoint,
                timeout=self.config.otlp_timeout_ms / 1000,
            )
            tracer_provider.add_span_processor(
                BatchSpanProcessor(span_exporter, schedule_delay_millis=self.config.export_interval_ms)
            )
            logger.info(f"✓ OTLP gRPC span exporter configured ({self.config.otlp_endpoint})")

        elif self.config.export_protocol == ExportProtocol.JAEGER:
            jaeger_exporter = JaegerExporter(
                agent_host_name=self.config.jaeger_host,
                agent_port=self.config.jaeger_port,
            )
            tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
            logger.info(
                f"✓ Jaeger span exporter configured "
                f"({self.config.jaeger_host}:{self.config.jaeger_port})"
            )

        if self.config.enable_debug_exporter:
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
            logger.info("✓ Console span exporter enabled (DEBUG)")

        return tracer_provider

    def _init_meter_provider(self, resource: Resource) -> MeterProvider:
        """Initialize MeterProvider with exporters."""

        readers = []

        # Add metric exporters
        if self.config.export_protocol == ExportProtocol.OTLP_GRPC:
            metric_exporter = OTLPMetricExporter(
                endpoint=self.config.otlp_endpoint,
                timeout=self.config.otlp_timeout_ms / 1000,
            )
            reader = PeriodicExportingMetricReader(
                metric_exporter,
                interval_millis=self.config.export_interval_ms,
            )
            readers.append(reader)
            logger.info(f"✓ OTLP gRPC metric exporter configured")

        elif self.config.export_protocol == ExportProtocol.JAEGER:
            # Jaeger also supports metrics
            metric_exporter = OTLPMetricExporter(endpoint=self.config.otlp_endpoint)
            reader = PeriodicExportingMetricReader(metric_exporter)
            readers.append(reader)
            logger.info(f"✓ Jaeger metric exporter configured")

        if self.config.enable_debug_exporter:
            from opentelemetry.sdk.metrics.export import ConsoleMetricExporter

            debug_exporter = ConsoleMetricExporter()
            debug_reader = PeriodicExportingMetricReader(debug_exporter)
            readers.append(debug_reader)
            logger.info("✓ Console metric exporter enabled (DEBUG)")

        meter_provider = MeterProvider(resource=resource, metric_readers=readers)
        return meter_provider

    def _create_sampler(self):
        """Create trace sampler based on strategy."""

        if self.config.sampling_strategy == SamplingStrategy.ALWAYS_ON:
            return trace.ALWAYS_ON
        elif self.config.sampling_strategy == SamplingStrategy.ALWAYS_OFF:
            return trace.ALWAYS_OFF
        elif self.config.sampling_strategy == SamplingStrategy.PROBABILITY:
            return TraceIdRatioBased(self.config.sampling_probability)
        else:
            # Default to probability sampling
            return TraceIdRatioBased(self.config.sampling_probability)

    def _init_instrumentations(self) -> None:
        """Initialize instrumentation libraries."""

        if self.config.enable_logging_instrumentation:
            LoggingInstrumentor().instrument()
            logger.info("✓ Logging instrumentation enabled")

        if self.config.enable_requests_instrumentation:
            RequestsInstrumentor().instrument()
            logger.info("✓ Requests instrumentation enabled")

    def get_tracer(self, name: str) -> trace.Tracer:
        """Get tracer for module."""
        if self.tracer_provider is None:
            raise RuntimeError("TracerProvider not initialized")
        return self.tracer_provider.get_tracer(name)

    def get_meter(self, name: str) -> metrics.Meter:
        """Get meter for module."""
        if self.meter_provider is None:
            raise RuntimeError("MeterProvider not initialized")
        return self.meter_provider.get_meter(name)

    def shutdown(self) -> None:
        """Shutdown SDK and flush pending data."""

        logger.info("Shutting down OpenTelemetry SDK...")

        if self.tracer_provider:
            self.tracer_provider.force_flush(timeout_millis=5000)
            self.tracer_provider.shutdown()
            logger.info("✓ TracerProvider shutdown")

        if self.meter_provider:
            self.meter_provider.force_flush(timeout_millis=5000)
            self.meter_provider.shutdown()
            logger.info("✓ MeterProvider shutdown")

        logger.info("✅ OpenTelemetry SDK shutdown complete")

    def get_status(self) -> Dict[str, Any]:
        """Get SDK status."""

        return {
            "service": self.config.service_name,
            "version": self.config.service_version,
            "environment": self.config.environment,
            "export_protocol": self.config.export_protocol.value,
            "export_enabled": self.config.export_enabled,
            "tracing_enabled": self.config.enable_traces,
            "metrics_enabled": self.config.enable_metrics,
            "sampling_strategy": self.config.sampling_strategy.value,
            "sampling_probability": self.config.sampling_probability,
            "tracer_provider_initialized": self.tracer_provider is not None,
            "meter_provider_initialized": self.meter_provider is not None,
        }


# Global SDK instance (singleton pattern)
_telemetry_sdk: Optional[TelemetrySDK] = None


def initialize_telemetry(config: Optional[TelemetryConfig] = None) -> TelemetrySDK:
    """
    Initialize global OpenTelemetry SDK.

    Call this once at application startup.

    Args:
        config: TelemetryConfig (uses defaults if None)

    Returns:
        Global TelemetrySDK instance
    """

    global _telemetry_sdk

    if _telemetry_sdk is not None:
        logger.warning("OpenTelemetry SDK already initialized")
        return _telemetry_sdk

    # Load config from environment if available
    if config is None:
        config = _load_config_from_env()

    _telemetry_sdk = TelemetrySDK(config)
    _telemetry_sdk.initialize()

    return _telemetry_sdk


def get_telemetry_sdk() -> Optional[TelemetrySDK]:
    """Get global TelemetrySDK instance."""
    return _telemetry_sdk


def get_global_tracer() -> Optional[trace.Tracer]:
    """Get global tracer."""
    if _telemetry_sdk:
        return _telemetry_sdk.tracer
    return None


def get_global_meter() -> Optional[metrics.Meter]:
    """Get global meter."""
    if _telemetry_sdk:
        return _telemetry_sdk.meter
    return None


def shutdown_telemetry() -> None:
    """Shutdown global OpenTelemetry SDK."""
    global _telemetry_sdk
    if _telemetry_sdk:
        _telemetry_sdk.shutdown()
        _telemetry_sdk = None


def _load_config_from_env() -> TelemetryConfig:
    """Load TelemetryConfig from environment variables."""

    config = TelemetryConfig()

    # Service attributes
    config.service_name = os.getenv("OTEL_SERVICE_NAME", config.service_name)
    config.service_version = os.getenv("OTEL_SERVICE_VERSION", config.service_version)
    config.environment = os.getenv("OTEL_ENVIRONMENT", config.environment)

    # Export protocol
    protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc").lower()
    if protocol == "grpc":
        config.export_protocol = ExportProtocol.OTLP_GRPC
    elif protocol == "jaeger":
        config.export_protocol = ExportProtocol.JAEGER
    else:
        config.export_protocol = ExportProtocol.OTLP_GRPC

    # OTLP configuration
    config.otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", config.otlp_endpoint)
    config.otlp_timeout_ms = int(os.getenv("OTEL_EXPORTER_OTLP_TIMEOUT", config.otlp_timeout_ms))

    # Jaeger configuration
    config.jaeger_host = os.getenv("OTEL_EXPORTER_JAEGER_HOST", config.jaeger_host)
    config.jaeger_port = int(os.getenv("OTEL_EXPORTER_JAEGER_PORT", config.jaeger_port))

    # Sampling
    sampling_strategy = os.getenv("OTEL_TRACES_SAMPLER", "probability").lower()
    if sampling_strategy == "always_on":
        config.sampling_strategy = SamplingStrategy.ALWAYS_ON
    elif sampling_strategy == "always_off":
        config.sampling_strategy = SamplingStrategy.ALWAYS_OFF
    else:
        config.sampling_strategy = SamplingStrategy.PROBABILITY

    config.sampling_probability = float(
        os.getenv("OTEL_TRACES_SAMPLER_ARG", str(config.sampling_probability))
    )

    # Feature flags
    config.enable_traces = os.getenv("OTEL_TRACES_ENABLED", "true").lower() == "true"
    config.enable_metrics = os.getenv("OTEL_METRICS_ENABLED", "true").lower() == "true"
    config.enable_logging_instrumentation = (
        os.getenv("OTEL_LOGGING_INSTRUMENTATION", "true").lower() == "true"
    )
    config.enable_debug_exporter = os.getenv("OTEL_DEBUG_EXPORTER", "false").lower() == "true"

    return config
