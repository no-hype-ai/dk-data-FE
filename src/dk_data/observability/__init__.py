"""OpenTelemetry instrumentation for dk-data-fe.

Feature: 002-production-readiness
Task: T056

This module provides centralized telemetry setup for all dk-data-fe services.
It configures:
- Distributed tracing via OpenTelemetry
- Metrics via Prometheus
- Structured logging via structlog

Usage:
    from dk_data.observability import setup_telemetry
    setup_telemetry("job-trigger")  # Call once at service startup
"""

import os
import logging
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_NAMESPACE, DEPLOYMENT_ENVIRONMENT
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

logger = logging.getLogger(__name__)

_telemetry_initialized = False


def setup_telemetry(
    service_name: str,
    service_namespace: str = "dk-data-fe",
    environment: Optional[str] = None,
) -> None:
    """
    Initialize OpenTelemetry with OTLP exporter for distributed tracing.

    Args:
        service_name: Name of the service (e.g., "job-trigger", "postgrest-sidecar")
        service_namespace: Namespace for grouping services (default: "dk-data-fe")
        environment: Deployment environment (default: from ENVIRONMENT env var)

    Environment Variables:
        OTEL_EXPORTER_OTLP_ENDPOINT: OTLP collector endpoint (default: alloy.infra.svc.cluster.local:4317)
        ENVIRONMENT: Deployment environment (default: "dev")
        OTEL_ENABLED: Set to "false" to disable telemetry (useful for local dev)
    """
    global _telemetry_initialized

    if _telemetry_initialized:
        logger.debug("Telemetry already initialized, skipping")
        return

    # Check if telemetry is disabled
    if os.getenv("OTEL_ENABLED", "true").lower() == "false":
        logger.info("OpenTelemetry disabled via OTEL_ENABLED=false")
        return

    env = environment or os.getenv("ENVIRONMENT", "dev")

    # Create resource with service attributes
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_NAMESPACE: service_namespace,
        DEPLOYMENT_ENVIRONMENT: env,
        "service.version": os.getenv("SERVICE_VERSION", "0.1.0"),
    })

    # Configure trace provider
    provider = TracerProvider(resource=resource)

    # Set up OTLP exporter
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "alloy.infra.svc.cluster.local:4317")

    try:
        exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            insecure=True,  # Use insecure for internal cluster communication
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info(f"OpenTelemetry configured: endpoint={otlp_endpoint}, service={service_name}")
    except Exception as e:
        logger.warning(f"Failed to configure OTLP exporter: {e}. Traces will not be exported.")

    trace.set_tracer_provider(provider)

    # Auto-instrument common libraries
    try:
        RequestsInstrumentor().instrument()
        logger.debug("Instrumented: requests")
    except Exception as e:
        logger.debug(f"Could not instrument requests: {e}")

    try:
        Psycopg2Instrumentor().instrument()
        logger.debug("Instrumented: psycopg2")
    except Exception as e:
        logger.debug(f"Could not instrument psycopg2: {e}")

    _telemetry_initialized = True


def get_tracer(name: str = __name__) -> trace.Tracer:
    """Get a tracer for the given module name."""
    return trace.get_tracer(name)


# Re-export commonly used components
from .metrics import (
    setup_metrics,
    record_job_duration,
    record_job_records,
    increment_job_failure,
    record_data_source_refresh,
)
from .logging import setup_logging, get_logger

__all__ = [
    "setup_telemetry",
    "get_tracer",
    "setup_metrics",
    "setup_logging",
    "get_logger",
    "record_job_duration",
    "record_job_records",
    "increment_job_failure",
    "record_data_source_refresh",
]
