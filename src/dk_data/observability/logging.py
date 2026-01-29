"""Structured logging configuration for dk-data-fe.

Feature: 002-production-readiness
Task: T058

Configures structlog for JSON-formatted logs compatible with Loki.
Includes automatic trace context injection for log correlation.

Log Format (JSON):
{
    "timestamp": "2026-01-20T10:30:00.000Z",
    "level": "INFO",
    "message": "Human-readable message",
    "service": "job-trigger",
    "trace_id": "hex-trace-id",
    "span_id": "hex-span-id",
    "context": { ... }
}
"""

import logging
import sys
import os
from typing import Optional

import structlog
from opentelemetry import trace


def add_trace_context(logger, method_name, event_dict):
    """Add OpenTelemetry trace context to log entries."""
    span = trace.get_current_span()
    if span.is_recording():
        ctx = span.get_span_context()
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


def add_service_context(service_name: str):
    """Create a processor that adds service name to all logs."""
    def processor(logger, method_name, event_dict):
        event_dict["service"] = service_name
        return event_dict
    return processor


def setup_logging(
    service_name: str,
    level: str = "INFO",
    json_format: bool = True,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        service_name: Name of the service for log context
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_format: If True, output JSON logs; if False, use console format

    Environment Variables:
        LOG_LEVEL: Override log level
        LOG_FORMAT: "json" or "console"
    """
    # Allow environment override
    level = os.getenv("LOG_LEVEL", level).upper()
    log_format = os.getenv("LOG_FORMAT", "json" if json_format else "console")

    # Determine processors based on format
    shared_processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        add_service_context(service_name),
        add_trace_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level),
    )

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger

    Usage:
        logger = get_logger(__name__)
        logger.info("Processing started", job_name="cms-inpatient", records=1500)
    """
    return structlog.get_logger(name)


class LoggerContextManager:
    """Context manager for adding temporary context to logs."""

    def __init__(self, logger: structlog.stdlib.BoundLogger, **context):
        self.logger = logger
        self.context = context
        self._token = None

    def __enter__(self):
        self._token = structlog.contextvars.bind_contextvars(**self.context)
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._token:
            structlog.contextvars.unbind_contextvars(*self.context.keys())
        return False


def with_context(logger: structlog.stdlib.BoundLogger, **context):
    """
    Add temporary context to a logger.

    Usage:
        with with_context(logger, job_id="123", source="cms"):
            logger.info("Processing...")  # Includes job_id and source
    """
    return LoggerContextManager(logger, **context)
