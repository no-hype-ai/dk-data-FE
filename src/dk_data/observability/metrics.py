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

DATA_SOURCE_TABLE_SIZE_BYTES = Gauge(
    "dk_data_source_table_size_bytes",
    "Storage size of data source table in bytes",
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

DK_SILVER_UNPROCESSED = Gauge(
    "dk_silver_unprocessed_total",
    "Unprocessed records in silver layer (bronze records pending silver transformation)",
    ["source"],
)

DK_GOLD_UNPROCESSED = Gauge(
    "dk_gold_unprocessed_total",
    "Unprocessed records in gold layer (silver molecules pending gold aggregation)",
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

DK_PIPELINE_DUPLICATE_FETCHES = Counter(
    "dk_pipeline_duplicate_fetches_total",
    "Total duplicate fetches detected via response_body_hash match (insert skipped)",
    ["source"],
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
# Prestaged Hydration Row-Count Gate (plan.md §B.3 / PR-02)
# =============================================================================
# Emitted by src/dk_data/ingestion/prestaged.py after the post-restore
# COUNT(*) block. Two counters, zero gauges: gauges would reset across
# job restarts and we only care about cumulative events for alerting
# (DkHydrationRowMismatch in plan.md §B.5).

DK_HYDRATION_ROW_MISMATCH_TOTAL = Counter(
    "dk_hydration_row_mismatch_total",
    (
        "Count of prestaged hydration steps where post-restore COUNT(*) "
        "deviated from the manifest's expected row_count beyond tolerance."
    ),
    ["source", "schema", "table"],
)

DK_HYDRATION_MANIFEST_MISSING_TOTAL = Counter(
    "dk_hydration_manifest_missing_total",
    (
        "Count of prestaged hydration steps where no manifest entry was "
        "found for the (schema, table). Row-count gate is disabled for "
        "this step; metric makes the gap visible instead of silent."
    ),
    ["source", "schema", "table"],
)


# =============================================================================
# NEW: Quarantine Metric (013-dk-data-observability — RC8)
# =============================================================================

DK_QUARANTINE_COUNT = Gauge(
    "dk_quarantine_count",
    "Number of molecules in quarantine status (agents.agent_quarantine)",
)


# =============================================================================
# CMS PUF Platform Metrics (019-cms-puf-platform-reconciliation)
# =============================================================================

CMS_SOURCE_HEALTH_STATUS = Gauge(
    "cms_source_health_status",
    "CMS data source health: 1=healthy (refreshed within threshold), 0=error",
    ["source"],
)

CMS_SOURCE_LAST_SYNC_TIMESTAMP = Gauge(
    "cms_source_last_sync_timestamp",
    "Unix timestamp of last successful CMS source sync",
    ["source"],
)

CMS_RECORDS_INGESTED_TOTAL = Counter(
    "cms_records_ingested_total",
    "Total records ingested per CMS data source",
    ["source"],
)

CMS_BACKFILL_REQUESTS_TOTAL = Counter(
    "cms_backfill_requests_total",
    "Total backfill requests triggered via data-tools API",
    ["source_name", "status"],
)

CMS_AGENT_COST_USD = Gauge(
    "cms_agent_cost_usd",
    "Estimated LLM cost (USD) for last agent run",
    ["agent_name"],
)

CMS_AGENT_QUARANTINE_PENDING = Gauge(
    "cms_agent_quarantine_pending",
    "Records quarantined in the most recent agent run",
    ["agent_name"],
)

CMS_AGENT_RECORDS_ENRICHED_TOTAL = Counter(
    "cms_agent_records_enriched_total",
    "Cumulative records successfully written to silver by agent",
    ["agent_name"],
)

CMS_AGENT_RECORDS_QUARANTINED_TOTAL = Counter(
    "cms_agent_records_quarantined_total",
    "Cumulative records quarantined by agent (low-confidence or error)",
    ["agent_name"],
)

CMS_AGENT_LAST_RUN_STATUS = Gauge(
    "cms_agent_last_run_status",
    "Status of last agent run: 1=success, 0=error",
    ["agent_name"],
)

CMS_AGENT_EXECUTIONS_TOTAL = Counter(
    "cms_agent_executions_total",
    "Total agent run invocations",
    ["agent_name"],
)

CMS_FETCH_DURATION_SECONDS = Histogram(
    "cms_fetch_duration_seconds",
    "Duration of CMS source fetch/ingestion jobs in seconds",
    ["source"],
    buckets=[30, 60, 120, 300, 600, 1200, 1800, 3600],
)

CMS_EXTERNAL_API_REQUESTS_TOTAL = Counter(
    "cms_external_api_requests_total",
    "Total HTTP requests made to external APIs (EuropePMC, NIH Reporter)",
    ["source", "status"],
)

CMS_RATE_LIMIT_REJECTIONS_TOTAL = Counter(
    "cms_rate_limit_rejections_total",
    "Total rate-limit (429) responses from external APIs",
    ["source"],
)

# Download integrity (Horizon 1 / plan §B.4)
DK_ARTIFACT_SIZE_MISMATCH_TOTAL = Counter(
    "dk_artifact_size_mismatch_total",
    "Total downloads where bytes written != Content-Length header",
    ["source"],
)

# =============================================================================
# Hydration observability expansion (Horizon 2 / plan §C.6)
#
# These three metrics are DEFINED here but EMISSION happens in the pre-staged
# hydration pipeline on feature/005-prestaged-hydration (follow-up PR after
# feature/005 merges to main). The dashboards at
# grafana/dashboards/applications/dk-data-fe-hydration.json and
# grafana/dashboards/applications/dk-data-fe-source-registry.json already
# reference them so they light up the moment emission lands.
# =============================================================================

# HIGH-CARDINALITY WARNING: labels = source × schema × table × phase. With
# ~73 sources × ~3 schemas × ~15 tables × 5 phases this can reach ~16k active
# series per bucket boundary. Prefer aggregating at dashboard-query time
# (sum by (source, phase, le) ...) rather than per-(schema, table). If the
# series count becomes a pressure point, drop `table` from the label set and
# fold it into a per-table `info` counter.
DK_HYDRATION_PHASE_SECONDS = Histogram(
    "dk_hydration_phase_seconds",
    "Time spent in each hydration phase per (source, schema, table); "
    "phase ∈ {download, validate, restore, rowcount, manifest_lookup}. "
    "Emitted by src/dk_data/ingestion/prestaged.py (feature/005).",
    ["source", "schema", "table", "phase"],
    buckets=(0.1, 0.5, 1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
)

# Bytes moved during hydration. kind ∈ {download, extracted} — `download` is
# wire bytes (Content-Length), `extracted` is on-disk bytes after tarball /
# zip / pg_dump expansion. Both are monotonically-increasing counters.
DK_ARTIFACT_BYTES_TOTAL = Counter(
    "dk_artifact_bytes_total",
    "Total bytes moved during hydration, by source and kind "
    "(kind ∈ {download, extracted}). Emitted by prestaged hydration and "
    "live-fetcher ingestion paths (feature/005 follow-up).",
    ["source", "kind"],
)

# Unix timestamp (seconds) of the most recent successful end-to-end hydration
# for a source. Consumers: freshness dashboards + "stale source" alerts
# (time() - dk_source_last_success_timestamp > sla_seconds).
DK_SOURCE_LAST_SUCCESS_TIMESTAMP = Gauge(
    "dk_source_last_success_timestamp",
    "Unix timestamp of the last successful hydration per source. "
    "Set on successful completion of run_ingestion() / prestaged loader "
    "(feature/005 follow-up). Panels compute freshness as "
    "(time() - dk_source_last_success_timestamp).",
    ["source"],
)

# =============================================================================
# Download integrity pipeline (Horizon 2 / plan §C.4)
# =============================================================================

# Incremented when a re-downloaded (source, url) has a sha256 that differs
# from the most recent prior row in meta.artifact_provenance. Signals that
# downstream transforms (bronze → silver) must re-run even if row counts
# match — the bits changed, the semantics may have changed.
DK_ARTIFACT_CHANGED_TOTAL = Counter(
    "dk_artifact_changed_total",
    "Total re-downloads where sha256 differs from the prior provenance row",
    ["source"],
)

# Incremented when the provenance writer itself fails (DB error, network
# blip, transient) — the download still succeeds (failure is swallowed so
# it cannot fail the ingestion), but we need visibility into how often
# provenance writes miss so we can detect silent drift.
DK_ARTIFACT_PROVENANCE_WRITE_ERRORS_TOTAL = Counter(
    "dk_artifact_provenance_write_errors_total",
    "Total failures writing to meta.artifact_provenance (swallowed, non-fatal)",
    ["source"],
)

# =============================================================================
# WAL backpressure — per-source budget exhaustion (Horizon 2 / plan §C.2)
# =============================================================================

# Incremented exactly once per (run, source) when a single source has
# consumed its WAL_PAUSE_BUDGET_PER_SOURCE_SECONDS share of the pause
# budget. After exhaustion, the throttle stops pausing for that source
# (so it races through without backpressure for the rest of the run)
# but continues to honour per-source budgets for every other source.
# Consumed by the DkWalSourceBudgetExhausted PrometheusRule (alert-
# driven, not a dashboard panel — any non-zero rate is an anomaly that
# pages on-call).
DK_WAL_SOURCE_BUDGET_EXHAUSTED_TOTAL = Counter(
    "dk_wal_source_budget_exhausted_total",
    "Total times a source exhausted its per-source WAL pause budget (plan §C.2)",
    ["source"],
)

CMS_GOLD_VIEW_LAST_REFRESH_TIMESTAMP = Gauge(
    "cms_gold_view_last_refresh_timestamp",
    "Unix timestamp of last hcs_gold view refresh",
    ["view"],
)

CMS_GOLD_VIEW_RECORD_COUNT = Gauge(
    "cms_gold_view_record_count",
    "Current record count in hcs_gold views",
    ["view"],
)

CMS_GOLD_REFRESH_DURATION_SECONDS = Gauge(
    "cms_gold_refresh_duration_seconds",
    "Duration in seconds of last hcs_gold materialized view refresh",
    ["view"],
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
    table_size_bytes: Optional[int] = None,
) -> None:
    """Record data source refresh metrics."""
    ts = refresh_timestamp or time.time()
    DATA_SOURCE_LAST_REFRESH_TIMESTAMP.labels(
        source_id=source_id, source_name=source_name
    ).set(ts)
    DATA_SOURCE_ROW_COUNT.labels(
        source_id=source_id, source_name=source_name
    ).set(row_count)
    if table_size_bytes is not None:
        DATA_SOURCE_TABLE_SIZE_BYTES.labels(
            source_id=source_id, source_name=source_name
        ).set(table_size_bytes)


def get_metrics() -> bytes:
    """Generate Prometheus metrics output."""
    return generate_latest(REGISTRY)


def get_metrics_content_type() -> str:
    """Get content type for metrics endpoint."""
    return CONTENT_TYPE_LATEST


_CMS_SOURCE_PREFIXES = (
    "cms_", "fetch-cms-", "fetch_cms_",
)


def _is_cms_source(name: str) -> bool:
    """Return True if the job/source name belongs to a CMS PUF source."""
    return any(name.startswith(p) for p in _CMS_SOURCE_PREFIXES)


def record_cms_source_sync(source_name: str, status: str, records: int = 0) -> None:
    """Record a CMS source sync event (health + timestamp + ingested counter)."""
    label = source_name.replace("-", "_").removeprefix("fetch_")
    if status == "success":
        CMS_SOURCE_HEALTH_STATUS.labels(source=label).set(1)
        CMS_SOURCE_LAST_SYNC_TIMESTAMP.labels(source=label).set(time.time())
        if records:
            CMS_RECORDS_INGESTED_TOTAL.labels(source=label).inc(records)
    else:
        CMS_SOURCE_HEALTH_STATUS.labels(source=label).set(0)


def record_cms_backfill(source_name: str, status: str) -> None:
    """Increment the backfill request counter for a CMS source."""
    CMS_BACKFILL_REQUESTS_TOTAL.labels(source_name=source_name, status=status).inc()


def record_agent_run(
    agent_name: str,
    records_written: int = 0,
    records_quarantined: int = 0,
    cost_usd: float = 0.0,
    status: str = "success",
) -> None:
    """Record agent run results: all CMS agent metrics."""
    CMS_AGENT_EXECUTIONS_TOTAL.labels(agent_name=agent_name).inc()
    CMS_AGENT_LAST_RUN_STATUS.labels(agent_name=agent_name).set(1 if status == "success" else 0)
    CMS_AGENT_QUARANTINE_PENDING.labels(agent_name=agent_name).set(records_quarantined)
    if records_written > 0:
        CMS_AGENT_RECORDS_ENRICHED_TOTAL.labels(agent_name=agent_name).inc(records_written)
    if records_quarantined > 0:
        CMS_AGENT_RECORDS_QUARANTINED_TOTAL.labels(agent_name=agent_name).inc(records_quarantined)
    if cost_usd > 0:
        CMS_AGENT_COST_USD.labels(agent_name=agent_name).set(cost_usd)


def record_cms_fetch_duration(source_name: str, duration_seconds: float) -> None:
    """Record fetch/ingestion job duration for a CMS source."""
    label = source_name.replace("-", "_").removeprefix("fetch_")
    CMS_FETCH_DURATION_SECONDS.labels(source=label).observe(duration_seconds)


def record_api_request(source: str, status: str = "success") -> None:
    """Record an external API request (EuropePMC, NIH Reporter)."""
    CMS_EXTERNAL_API_REQUESTS_TOTAL.labels(source=source, status=status).inc()


def record_rate_limit_rejection(source: str) -> None:
    """Record a 429 rate-limit rejection from an external API."""
    CMS_RATE_LIMIT_REJECTIONS_TOTAL.labels(source=source).inc()


def record_gold_view_refresh(view: str, record_count: int, duration_seconds: float = 0.0) -> None:
    """Record an hcs_gold view refresh event."""
    CMS_GOLD_VIEW_LAST_REFRESH_TIMESTAMP.labels(view=view).set(time.time())
    CMS_GOLD_VIEW_RECORD_COUNT.labels(view=view).set(record_count)
    if duration_seconds > 0:
        CMS_GOLD_REFRESH_DURATION_SECONDS.labels(view=view).set(duration_seconds)


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
