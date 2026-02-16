"""Prometheus metrics for dk-data-fe.

Feature: 002-production-readiness
Task: T057

Defines standard metrics for monitoring data platform health.
Metrics are exposed via /metrics endpoint in FastAPI services.

Metric Naming Convention:
- Prefix: dk_data_ (for data-platform-specific metrics)
- http_ (for standard HTTP metrics via opentelemetry)
- batch_job_ (for batch job metrics)
"""

import time
from typing import Optional
from functools import wraps

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    REGISTRY,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

# =============================================================================
# IP Data Sources (014-uspto-euipo-model-datasource)
# =============================================================================

IP_DATA_SOURCES = [
    'uspto_patents',
    'uspto_ci',
    'epo_patents',
    'uspto_trademarks',
    'euipo_trademarks',
]

# =============================================================================
# HTTP Metrics (supplementary to OpenTelemetry auto-instrumentation)
# =============================================================================

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# =============================================================================
# Database Metrics
# =============================================================================

DB_QUERY_DURATION_SECONDS = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["query_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

# =============================================================================
# Batch Job Metrics
# =============================================================================

BATCH_JOB_DURATION_SECONDS = Histogram(
    "batch_job_duration_seconds",
    "Batch job execution duration in seconds",
    ["job_name"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)

BATCH_JOB_RECORDS_PROCESSED = Counter(
    "batch_job_records_processed",
    "Total records processed by batch jobs",
    ["job_name"],
)

BATCH_JOB_FAILURES_TOTAL = Counter(
    "batch_job_failures_total",
    "Total batch job failures",
    ["job_name"],
)

BATCH_JOB_LAST_SUCCESS_TIMESTAMP = Gauge(
    "batch_job_last_success_timestamp",
    "Timestamp of last successful job completion",
    ["job_name"],
)

# =============================================================================
# Data Source Metrics
# =============================================================================

DATA_SOURCE_LAST_REFRESH_TIMESTAMP = Gauge(
    "dk_data_source_last_refresh_timestamp",
    "Unix timestamp of last data source refresh",
    ["source_id", "source_name"],
)

DATA_SOURCE_ROW_COUNT = Gauge(
    "dk_data_source_row_count",
    "Current row count for data source",
    ["source_id", "source_name"],
)

DATA_SOURCE_STALENESS_HOURS = Gauge(
    "dk_data_source_staleness_hours",
    "Hours since last data source refresh",
    ["source_id", "source_name"],
)


# =============================================================================
# Helper Functions
# =============================================================================

def setup_metrics() -> None:
    """Initialize metrics (called at service startup)."""
    # Metrics are automatically registered with the default registry
    pass


def record_job_duration(job_name: str, duration_seconds: float) -> None:
    """Record batch job duration."""
    BATCH_JOB_DURATION_SECONDS.labels(job_name=job_name).observe(duration_seconds)


def record_job_records(job_name: str, count: int) -> None:
    """Record number of records processed by a batch job."""
    BATCH_JOB_RECORDS_PROCESSED.labels(job_name=job_name).inc(count)


def increment_job_failure(job_name: str) -> None:
    """Increment job failure counter."""
    BATCH_JOB_FAILURES_TOTAL.labels(job_name=job_name).inc()


def mark_job_success(job_name: str) -> None:
    """Mark job as successful (updates last success timestamp)."""
    BATCH_JOB_LAST_SUCCESS_TIMESTAMP.labels(job_name=job_name).set(time.time())


def record_data_source_refresh(
    source_id: str,
    source_name: str,
    row_count: int,
    refresh_timestamp: Optional[float] = None,
) -> None:
    """Record data source refresh metrics."""
    ts = refresh_timestamp or time.time()
    DATA_SOURCE_LAST_REFRESH_TIMESTAMP.labels(
        source_id=source_id, source_name=source_name
    ).set(ts)
    DATA_SOURCE_ROW_COUNT.labels(
        source_id=source_id, source_name=source_name
    ).set(row_count)


def get_metrics() -> bytes:
    """Generate Prometheus metrics output."""
    return generate_latest(REGISTRY)


def get_metrics_content_type() -> str:
    """Get content type for metrics endpoint."""
    return CONTENT_TYPE_LATEST


def timed_job(job_name: str):
    """Decorator to automatically time and record job metrics."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                mark_job_success(job_name)
                return result
            except Exception:
                increment_job_failure(job_name)
                raise
            finally:
                duration = time.time() - start
                record_job_duration(job_name, duration)
        return wrapper
    return decorator
