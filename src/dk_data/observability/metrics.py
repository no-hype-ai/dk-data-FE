"""Consolidated Prometheus metrics for dk-data-fe.

Feature: 013-dk-data-observability
Supersedes: 002-production-readiness (T057)

Single source of truth for ALL Prometheus metric definitions.
Metrics are exposed via /metrics endpoint in FastAPI services.

Previously metrics were scattered across 4 files:
- observability/metrics.py (this file, canonical)
- services/data_platform/metrics.py (now imports from here)
- services/data_platform/pipeline_monitoring.py (now imports from here)
- api/routes/monitoring.py (now imports from here)

Metric Naming Convention:
- http_       — Standard HTTP metrics (supplementary to OTel auto-instrumentation)
- db_         — Database query metrics
- batch_job_  — Batch job execution metrics
- dk_data_    — Data source freshness/staleness metrics
- dk_         — Platform entity, pipeline, layer, and resolution metrics
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
# Data Source Freshness Metrics
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
# Platform Entity Metrics (from services/data_platform/metrics.py)
# =============================================================================

DK_MOLECULES_TOTAL = Gauge(
    "dk_molecules_total",
    "Total molecules in the platform",
    ["status"],
)

DK_CLINICAL_TRIALS_TOTAL = Gauge(
    "dk_clinical_trials_total",
    "Total clinical trials tracked",
    ["status"],
)

DK_ADVERSE_EVENTS_TOTAL = Gauge(
    "dk_adverse_events_reports_total",
    "Total adverse event reports",
)

DK_RESOLUTION_QUEUE_PENDING = Gauge(
    "dk_resolution_queue_pending_total",
    "Pending items in entity resolution queue",
)

DK_MOLECULES_BY_LIFECYCLE_STAGE = Gauge(
    "dk_molecules_by_lifecycle_stage",
    "Molecules by lifecycle stage",
    ["stage"],
)

DK_TRIALS_BY_PHASE = Gauge(
    "dk_clinical_trials_by_phase",
    "Clinical trials by phase",
    ["phase"],
)

DK_ENTITY_RESOLUTION_SUCCESS_RATE = Gauge(
    "dk_entity_resolution_success_rate",
    "Entity resolution success rate (0-1)",
)

DK_SOURCE_LAST_SYNC = Gauge(
    "dk_source_last_sync_timestamp",
    "Unix timestamp of last successful sync",
    ["source"],
)

DK_SOURCE_HEALTH_STATUS = Gauge(
    "dk_source_health_status",
    "Data source health status (healthy=1, stale=0.5, error=0)",
    ["source"],
)


# =============================================================================
# Pipeline Health Metrics (from services/data_platform/metrics.py — canonical)
# =============================================================================

DK_PIPELINE_RECORDS_PROCESSED = Counter(
    "dk_pipeline_records_processed_total",
    "Total records processed by pipeline",
    ["layer", "source"],
)

DK_PIPELINE_PROCESSING_DURATION = Histogram(
    "dk_pipeline_processing_duration_seconds",
    "Pipeline processing duration",
    ["layer"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

DK_PIPELINE_ERRORS = Counter(
    "dk_pipeline_errors_total",
    "Pipeline errors",
    ["layer", "error_type"],
)

DK_API_REQUESTS = Counter(
    "dk_api_requests_total",
    "API requests to data sources",
    ["source", "status"],
)

DK_ALERTS_ACTIVE = Gauge(
    "dk_alerts_active",
    "Currently active alerts",
    ["severity", "alert_type"],
)

DK_PIPELINE_JOBS_TOTAL = Counter(
    "dk_pipeline_jobs_total",
    "Total pipeline jobs executed",
    ["tier", "status"],
)

DK_PIPELINE_JOB_DURATION = Histogram(
    "dk_pipeline_job_duration_seconds",
    "Pipeline job total duration",
    ["tier"],
    buckets=[60, 300, 600, 1800, 3600, 7200, 14400],
)

DK_PIPELINE_LAST_SUCCESS = Gauge(
    "dk_pipeline_last_success_timestamp",
    "Unix timestamp of last successful pipeline run",
    ["tier"],
)

DK_PIPELINE_ACTIVE = Gauge(
    "dk_pipeline_active",
    "Whether a pipeline is currently running (1) or not (0)",
    ["tier"],
)

DK_LAYER_RECORD_COUNT = Gauge(
    "dk_layer_record_count",
    "Current record count per layer",
    ["layer"],
)

DK_RAW_UNPROCESSED = Gauge(
    "dk_raw_unprocessed_total",
    "Unprocessed records in raw layer",
    ["source"],
)

DK_BRONZE_UNPROCESSED = Gauge(
    "dk_bronze_unprocessed_total",
    "Unprocessed records in bronze layer",
    ["source"],
)

DK_TABLE_RECORD_COUNT = Gauge(
    "dk_table_record_count",
    "Record count per table",
    ["layer", "table_name"],
)


# =============================================================================
# Pipeline Run Metrics (from pipeline_monitoring.py — unique)
# =============================================================================

DK_PIPELINE_RUNS_TOTAL = Counter(
    "dk_pipeline_runs_total",
    "Total number of pipeline runs",
    ["layer", "source", "status"],
)

DK_PIPELINE_DURATION_SECONDS = Histogram(
    "dk_pipeline_duration_seconds",
    "Pipeline run duration in seconds",
    ["layer", "source"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],
)

DK_SOURCE_RECORDS_TOTAL = Gauge(
    "dk_source_records_total",
    "Total records for source",
    ["source", "layer"],
)

DK_RESOLUTION_QUEUE_SIZE = Gauge(
    "dk_resolution_queue_size",
    "Number of items in resolution queue",
    ["priority"],
)

DK_RESOLUTION_SUCCESS_RATE = Gauge(
    "dk_resolution_success_rate",
    "Entity resolution success rate",
)

DK_MOLECULES_BY_STAGE = Gauge(
    "dk_molecules_by_stage",
    "Molecules by lifecycle stage",
    ["stage"],
)


# =============================================================================
# Bronze/Silver/Gold Layer Metrics (from api/routes/monitoring.py)
# =============================================================================

# Bronze Layer
DK_BRONZE_RECORDS_INGESTED = Counter(
    "dk_bronze_records_ingested_total",
    "Total records ingested into Bronze layer",
    ["source"],
)

DK_BRONZE_INGESTION_ERRORS = Counter(
    "dk_bronze_ingestion_errors_total",
    "Total ingestion errors by source",
    ["source", "error_type"],
)

DK_BRONZE_INGESTION_DURATION = Histogram(
    "dk_bronze_ingestion_duration_seconds",
    "Time spent on Bronze ingestion runs",
    ["source"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

DK_BRONZE_UNPROCESSED_RECORDS = Gauge(
    "dk_bronze_unprocessed_records",
    "Number of Bronze records pending Silver transformation",
    ["source"],
)

# Silver Layer
DK_SILVER_RECORDS_TRANSFORMED = Counter(
    "dk_silver_records_transformed_total",
    "Total records transformed to Silver layer",
    ["source_table"],
)

DK_SILVER_TRANSFORMATION_ERRORS = Counter(
    "dk_silver_transformation_errors_total",
    "Total transformation errors",
    ["source_table", "error_type"],
)

DK_SILVER_MOLECULES_TOTAL = Gauge(
    "dk_silver_molecules_total",
    "Total unique molecules in Silver layer",
)

DK_SILVER_IDENTIFIER_MAPPINGS = Gauge(
    "dk_silver_identifier_mappings_total",
    "Total identifier mappings",
    ["identifier_type"],
)

# Gold Layer
DK_GOLD_PROFILES_TOTAL = Gauge(
    "dk_gold_profiles_total",
    "Total molecule profiles in Gold layer",
)

DK_GOLD_AGGREGATION_DURATION = Histogram(
    "dk_gold_aggregation_duration_seconds",
    "Time spent on Gold aggregation",
    ["aggregation_type"],
    buckets=[10, 30, 60, 120, 300, 600, 1200],
)

# Resolution
DK_RESOLUTION_REQUESTS = Counter(
    "dk_resolution_requests_total",
    "Total identifier resolution requests",
    ["resolution_type"],
)

DK_RESOLUTION_LATENCY = Histogram(
    "dk_resolution_latency_seconds",
    "Latency of identifier resolution",
    ["resolution_type"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
)

DK_FUZZY_MATCH_REQUESTS = Counter(
    "dk_fuzzy_match_requests_total",
    "Total fuzzy matching requests",
)

DK_FUZZY_MATCH_RESULTS = Histogram(
    "dk_fuzzy_match_results_count",
    "Number of results returned per fuzzy match",
    buckets=[0, 1, 5, 10, 25, 50, 100],
)

# Onboarding
DK_ONBOARDING_STARTED = Counter(
    "dk_onboarding_started_total",
    "Total onboarding wizards started",
)

DK_ONBOARDING_COMPLETED = Counter(
    "dk_onboarding_completed_total",
    "Total onboarding wizards completed",
)

DK_ONBOARDING_STEP_DURATION = Histogram(
    "dk_onboarding_step_duration_seconds",
    "Time spent on each onboarding step",
    ["step_number"],
    buckets=[5, 15, 30, 60, 120, 300],
)

# Alerts
DK_ALERTS_GENERATED = Counter(
    "dk_alerts_generated_total",
    "Total alerts generated",
    ["alert_type", "severity"],
)

DK_ALERTS_DELIVERED = Counter(
    "dk_alerts_delivered_total",
    "Total alerts delivered",
    ["delivery_method"],
)


# =============================================================================
# NEW: Quarantine Metric (013-dk-data-observability — RC8)
# =============================================================================

DK_QUARANTINE_COUNT = Gauge(
    "dk_quarantine_count",
    "Number of molecules in quarantine status",
)


# =============================================================================
# Helper Functions
# =============================================================================

def setup_metrics() -> None:
    """Initialize metrics (called at service startup)."""
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
