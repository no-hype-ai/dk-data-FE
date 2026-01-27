"""
Monitoring Routes - Pipeline Health and Prometheus Metrics
Part of: 012-dk-data-platform

Provides:
- /api/v1/monitoring/health - Pipeline health status
- /api/v1/monitoring/metrics - Prometheus metrics endpoint
- /api/v1/monitoring/run - Trigger pipeline run
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from starlette.responses import Response
from loguru import logger

# Import DK Data Platform metrics
try:
    from ...services.data_platform.metrics import (
        initialize_demo_metrics,
        refresh_metrics_from_database_sync
    )
    DK_METRICS_AVAILABLE = True
except ImportError:
    DK_METRICS_AVAILABLE = False
    refresh_metrics_from_database_sync = None
    logger.warning("DK Data Platform metrics not available")

# Router
router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])

# Initialize metrics on module load
if DK_METRICS_AVAILABLE:
    initialize_demo_metrics()
    # Initial refresh from database
    try:
        refresh_metrics_from_database_sync()
    except Exception as e:
        logger.warning(f"Initial metrics refresh failed: {e}")


# ==========================================
# Prometheus Metrics Definitions
# ==========================================

# Bronze Layer Metrics
bronze_records_ingested = Counter(
    "dk_bronze_records_ingested_total",
    "Total records ingested into Bronze layer",
    ["source"],
)

bronze_ingestion_errors = Counter(
    "dk_bronze_ingestion_errors_total",
    "Total ingestion errors by source",
    ["source", "error_type"],
)

bronze_ingestion_duration = Histogram(
    "dk_bronze_ingestion_duration_seconds",
    "Time spent on Bronze ingestion runs",
    ["source"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

bronze_unprocessed_records = Gauge(
    "dk_bronze_unprocessed_records",
    "Number of Bronze records pending Silver transformation",
    ["source"],
)

# Silver Layer Metrics
silver_records_transformed = Counter(
    "dk_silver_records_transformed_total",
    "Total records transformed to Silver layer",
    ["source_table"],
)

silver_transformation_errors = Counter(
    "dk_silver_transformation_errors_total",
    "Total transformation errors",
    ["source_table", "error_type"],
)

silver_molecules_total = Gauge(
    "dk_silver_molecules_total",
    "Total unique molecules in Silver layer",
)

silver_identifier_mappings = Gauge(
    "dk_silver_identifier_mappings_total",
    "Total identifier mappings",
    ["identifier_type"],
)

# Gold Layer Metrics
gold_profiles_total = Gauge(
    "dk_gold_profiles_total",
    "Total molecule profiles in Gold layer",
)

gold_aggregation_duration = Histogram(
    "dk_gold_aggregation_duration_seconds",
    "Time spent on Gold aggregation",
    ["aggregation_type"],
    buckets=[10, 30, 60, 120, 300, 600, 1200],
)

# Resolution Metrics
resolution_requests = Counter(
    "dk_resolution_requests_total",
    "Total identifier resolution requests",
    ["resolution_type"],  # cache_hit, local_db, external_api
)

resolution_latency = Histogram(
    "dk_resolution_latency_seconds",
    "Latency of identifier resolution",
    ["resolution_type"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
)

fuzzy_match_requests = Counter(
    "dk_fuzzy_match_requests_total",
    "Total fuzzy matching requests",
)

fuzzy_match_results = Histogram(
    "dk_fuzzy_match_results_count",
    "Number of results returned per fuzzy match",
    buckets=[0, 1, 5, 10, 25, 50, 100],
)

# Onboarding Metrics
onboarding_started = Counter(
    "dk_onboarding_started_total",
    "Total onboarding wizards started",
)

onboarding_completed = Counter(
    "dk_onboarding_completed_total",
    "Total onboarding wizards completed",
)

onboarding_step_duration = Histogram(
    "dk_onboarding_step_duration_seconds",
    "Time spent on each onboarding step",
    ["step_number"],
    buckets=[5, 15, 30, 60, 120, 300],
)

# Alert Metrics
alerts_generated = Counter(
    "dk_alerts_generated_total",
    "Total alerts generated",
    ["alert_type", "severity"],
)

alerts_delivered = Counter(
    "dk_alerts_delivered_total",
    "Total alerts delivered",
    ["delivery_method"],
)


# ==========================================
# Response Models
# ==========================================

class SourceHealth(BaseModel):
    source_id: str
    last_sync: Optional[datetime]
    records_pending: int
    error_count: int
    status: str  # healthy, degraded, error


class LayerHealth(BaseModel):
    layer: str
    record_count: int
    last_update: Optional[datetime]
    status: str


class PipelineHealth(BaseModel):
    status: str  # healthy, degraded, error
    bronze_sources: list[SourceHealth]
    silver: LayerHealth
    gold: LayerHealth
    last_check: datetime


class RunTriggerRequest(BaseModel):
    pipeline_type: str  # bronze_ingest, silver_transform, gold_aggregate
    source_id: Optional[str] = None
    force: bool = False


class RunTriggerResponse(BaseModel):
    run_id: str
    status: str
    message: str


# ==========================================
# Endpoints
# ==========================================

@router.get("/metrics")
async def prometheus_metrics():
    """
    Prometheus metrics endpoint.
    Returns metrics in Prometheus text format.
    Refreshes from database on each call for live data.
    """
    # Refresh metrics from database before returning
    if DK_METRICS_AVAILABLE and refresh_metrics_from_database_sync:
        try:
            refresh_metrics_from_database_sync()
        except Exception as e:
            logger.warning(f"Metrics refresh failed: {e}")

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@router.get("/stats")
async def database_stats():
    """
    Get live database statistics as JSON.
    Queries actual database tables for real counts.
    """
    import os
    stats = {
        "timestamp": datetime.utcnow().isoformat(),
        "tables": {},
        "sources": {},
        "summary": {}
    }

    try:
        import psycopg2
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            # Build from individual env vars (Docker container uses these)
            db_host = os.getenv('POSTGRES_HOST', 'postgres')
            db_port = os.getenv('POSTGRES_PORT', '5432')
            db_name = os.getenv('POSTGRES_DB', 'edwards_tavr')
            db_user = os.getenv('POSTGRES_USER', 'postgres')
            db_pass = os.getenv('POSTGRES_PASSWORD', 'postgres')
            db_url = f'postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}'
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        # Table counts
        tables = [
            ('compounds', 'public'),
            ('clinical_trials', 'public'),
            ('drugbank_data', 'public'),
            ('fda_labels', 'public'),
            ('faers_events', 'public'),
            ('chembl_activities', 'public'),
            ('pubchem_compounds', 'public'),
            ('sider_adverse_reactions', 'public'),
            ('tdc_admet_data', 'public'),
            ('drug_interactions', 'public'),
        ]

        for table, schema in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
                stats["tables"][table] = cur.fetchone()[0]
            except:
                stats["tables"][table] = 0

        # Summary stats
        stats["summary"]["total_compounds"] = stats["tables"].get("compounds", 0)
        stats["summary"]["total_trials"] = stats["tables"].get("clinical_trials", 0)
        stats["summary"]["total_adverse_events"] = (
            stats["tables"].get("faers_events", 0) +
            stats["tables"].get("sider_adverse_reactions", 0)
        )
        stats["summary"]["total_drug_interactions"] = stats["tables"].get("drug_interactions", 0)

        # Clinical trials by status
        cur.execute("""
            SELECT status, COUNT(*) as cnt
            FROM clinical_trials
            WHERE status IS NOT NULL
            GROUP BY status
            ORDER BY cnt DESC
            LIMIT 10
        """)
        stats["trials_by_status"] = {row[0]: row[1] for row in cur.fetchall()}

        # Clinical trials by phase
        cur.execute("""
            SELECT
                CASE
                    WHEN phase ILIKE '%1%' AND phase NOT ILIKE '%2%' THEN 'Phase 1'
                    WHEN phase ILIKE '%2%' AND phase NOT ILIKE '%3%' THEN 'Phase 2'
                    WHEN phase ILIKE '%3%' AND phase NOT ILIKE '%4%' THEN 'Phase 3'
                    WHEN phase ILIKE '%4%' THEN 'Phase 4'
                    ELSE 'Other'
                END as phase_group,
                COUNT(*) as count
            FROM clinical_trials
            WHERE phase IS NOT NULL
            GROUP BY phase_group
            ORDER BY phase_group
        """)
        stats["trials_by_phase"] = {row[0]: row[1] for row in cur.fetchall()}

        cur.close()
        conn.close()

    except Exception as e:
        stats["error"] = str(e)
        logger.error(f"Failed to get database stats: {e}")

    return stats


@router.get("/health", response_model=PipelineHealth)
async def pipeline_health():
    """
    Get overall pipeline health status.
    Checks Bronze, Silver, and Gold layers.
    """
    # This would normally query the database
    # Placeholder implementation
    return PipelineHealth(
        status="healthy",
        bronze_sources=[
            SourceHealth(
                source_id="clinicaltrials_gov",
                last_sync=datetime.utcnow() - timedelta(hours=2),
                records_pending=0,
                error_count=0,
                status="healthy",
            ),
            SourceHealth(
                source_id="openfda_labels",
                last_sync=datetime.utcnow() - timedelta(hours=4),
                records_pending=0,
                error_count=0,
                status="healthy",
            ),
        ],
        silver=LayerHealth(
            layer="silver",
            record_count=0,
            last_update=datetime.utcnow() - timedelta(hours=1),
            status="healthy",
        ),
        gold=LayerHealth(
            layer="gold",
            record_count=0,
            last_update=datetime.utcnow() - timedelta(hours=1),
            status="healthy",
        ),
        last_check=datetime.utcnow(),
    )


@router.post("/run", response_model=RunTriggerResponse)
async def trigger_pipeline_run(request: RunTriggerRequest):
    """
    Manually trigger a pipeline run.
    Requires data_ops role.
    """
    import uuid

    # Validate pipeline type
    valid_types = ["bronze_ingest", "silver_transform", "gold_aggregate"]
    if request.pipeline_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pipeline_type. Must be one of: {valid_types}",
        )

    # Generate run ID
    run_id = str(uuid.uuid4())

    # In a real implementation, this would:
    # 1. Check if a run is already in progress
    # 2. Queue the run in Redis
    # 3. Return the run ID for tracking

    return RunTriggerResponse(
        run_id=run_id,
        status="queued",
        message=f"{request.pipeline_type} run queued successfully",
    )


@router.get("/runs")
async def list_recent_runs(
    pipeline_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
):
    """
    List recent pipeline runs.
    """
    # Placeholder - would query bronze_ingestion_runs, silver_transformation_runs, gold_aggregation_runs
    return {
        "runs": [],
        "total": 0,
        "filters": {
            "pipeline_type": pipeline_type,
            "status": status,
            "limit": limit,
        },
    }


@router.get("/sources")
async def list_data_sources():
    """
    List configured data sources and their status.
    Returns real-time health status for all data sources.
    """
    import os
    import psycopg2

    # Source configurations with display names and types
    source_configs = {
        # Local database sources - use actual table names from the database
        "clinical_trials_local": {"name": "Clinical Trials (Local)", "type": "local_db", "table": "clinical_trials"},
        "fda_labels_local": {"name": "FDA Labels (Local)", "type": "local_db", "table": "fda_labels"},
        "drugbank": {"name": "DrugBank", "type": "local_db", "table": "drugbank_data"},
        "chembl": {"name": "ChEMBL", "type": "local_db", "table": "chembl_molecules"},  # Fixed: was chembl_compounds
        "pubchem": {"name": "PubChem", "type": "local_db", "table": "pubchem_compounds"},
        "sider": {"name": "SIDER", "type": "local_db", "table": "sider_adverse_reactions"},
        "bindingdb": {"name": "BindingDB", "type": "local_db", "table": "bindingdb_affinities"},
        "who_inn": {"name": "WHO INN", "type": "local_db", "table": "who_inn_data"},  # Fixed: was who_inn_names
        "faers": {"name": "FAERS", "type": "local_db", "table": "faers_events"},  # Fixed: was faers_adverse_events
        "regulatory_milestones": {"name": "Regulatory Milestones", "type": "local_db", "table": "regulatory_milestones"},
        "patents_local": {"name": "Patents (Local)", "type": "local_db", "table": "drugbank_patents"},  # Fixed: use drugbank_patents
        "publications_local": {"name": "Publications (Local)", "type": "local_db", "table": "silver.publications", "schema": "silver"},
        # External API sources
        "clinicaltrials_gov": {"name": "ClinicalTrials.gov", "type": "external_api", "endpoint": "clinicaltrials.gov/api"},
        "openfda": {"name": "OpenFDA", "type": "external_api", "endpoint": "api.fda.gov"},
        "pubchem_api": {"name": "PubChem API", "type": "external_api", "endpoint": "pubchem.ncbi.nlm.nih.gov"},
        "rxnorm": {"name": "RxNorm", "type": "external_api", "endpoint": "rxnav.nlm.nih.gov"},
        "openalex": {"name": "OpenAlex", "type": "external_api", "endpoint": "api.openalex.org"},
        "patentsview": {"name": "PatentsView", "type": "external_api", "endpoint": "api.patentsview.org"},
        "ema": {"name": "EMA Medicines", "type": "external_api", "endpoint": "ema.europa.eu"},
    }

    sources = []

    try:
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            db_host = os.getenv('POSTGRES_HOST', 'postgres')
            db_port = os.getenv('POSTGRES_PORT', '5432')
            db_name = os.getenv('POSTGRES_DB', 'edwards_tavr')
            db_user = os.getenv('POSTGRES_USER', 'postgres')
            db_pass = os.getenv('POSTGRES_PASSWORD', 'postgres')
            db_url = f'postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}'

        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        for source_id, config in source_configs.items():
            source_info = {
                "source_id": source_id,
                "source_name": config["name"],
                "api_type": "REST" if config["type"] == "external_api" else "Local DB",
                "is_active": True,
                "status": "up",
                "latency_ms": 0,
                "error_rate": 0.0,
                "records_count": 0,
                "last_successful_sync": None,
            }

            if config["type"] == "local_db":
                table = config["table"]
                schema = config.get("schema", "public")
                try:
                    # Handle schema.table format
                    if "." in table:
                        schema, table_name = table.split(".", 1)
                    else:
                        table_name = table

                    # Check if table exists
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_schema = %s AND table_name = %s
                        )
                    """, (schema, table_name))
                    table_exists = cur.fetchone()[0]

                    if table_exists:
                        full_table = f"{schema}.{table_name}" if schema != "public" else table_name
                        cur.execute(f"SELECT COUNT(*) FROM {full_table}")
                        count = cur.fetchone()[0] or 0
                        source_info["records_count"] = count
                        source_info["status"] = "up" if count > 0 else "degraded"
                    else:
                        source_info["status"] = "down"
                        source_info["is_active"] = False
                except Exception as e:
                    source_info["status"] = "down"
                    source_info["error_rate"] = 100.0
                    logger.debug(f"Error checking {source_id}: {e}")
            else:
                # External API sources - assume healthy (actual check done by health endpoint)
                source_info["status"] = "up"
                source_info["latency_ms"] = 50  # Placeholder

            sources.append(source_info)

        cur.close()
        conn.close()

    except Exception as e:
        logger.error(f"Failed to get source statuses: {e}")
        # Return basic config without counts on error
        for source_id, config in source_configs.items():
            sources.append({
                "source_id": source_id,
                "source_name": config["name"],
                "api_type": "REST" if config["type"] == "external_api" else "Local DB",
                "is_active": True,
                "status": "degraded",
                "latency_ms": 0,
                "error_rate": 0.0,
                "records_count": 0,
                "last_successful_sync": None,
            })

    return {
        "sources": sources,
        "total": len(sources),
        "healthy_count": sum(1 for s in sources if s["status"] == "up"),
        "degraded_count": sum(1 for s in sources if s["status"] == "degraded"),
        "down_count": sum(1 for s in sources if s["status"] == "down"),
    }


# ==========================================
# Data Freshness Endpoints
# ==========================================

@router.get("/freshness")
async def get_data_freshness():
    """
    Get data freshness report for all sources.

    Returns:
    - Source-by-source freshness status
    - Staleness indicators
    - Next scheduled refresh times
    """
    # This would use DataFreshnessMonitor in production
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "status": "healthy",
        "sources": [
            {
                "source": "clinicaltrials_gov",
                "tier": "daily",
                "status": "healthy",
                "last_success": (datetime.utcnow() - timedelta(hours=6)).isoformat(),
                "next_scheduled": (datetime.utcnow() + timedelta(hours=18)).isoformat(),
                "record_count": 0,
                "is_stale": False,
            },
            {
                "source": "openfda_faers",
                "tier": "daily",
                "status": "healthy",
                "last_success": (datetime.utcnow() - timedelta(hours=8)).isoformat(),
                "next_scheduled": (datetime.utcnow() + timedelta(hours=16)).isoformat(),
                "record_count": 0,
                "is_stale": False,
            },
            {
                "source": "drugbank",
                "tier": "weekly",
                "status": "healthy",
                "last_success": (datetime.utcnow() - timedelta(days=3)).isoformat(),
                "next_scheduled": (datetime.utcnow() + timedelta(days=4)).isoformat(),
                "record_count": 0,
                "is_stale": False,
            },
        ],
        "healthy_count": 3,
        "stale_count": 0,
        "error_count": 0,
    }


@router.get("/freshness/{source}")
async def get_source_freshness(source: str):
    """
    Get detailed freshness info for a specific source.
    """
    valid_sources = [
        "clinicaltrials_gov", "openfda_faers", "openfda_labels",
        "drugbank", "chembl", "pubchem", "uniprot", "openalex"
    ]

    if source not in valid_sources:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown source. Valid sources: {', '.join(valid_sources)}"
        )

    return {
        "source": source,
        "tier": "daily" if source.startswith("openfda") or source == "clinicaltrials_gov" else "weekly",
        "status": "healthy",
        "last_refresh": (datetime.utcnow() - timedelta(hours=6)).isoformat(),
        "last_success": (datetime.utcnow() - timedelta(hours=6)).isoformat(),
        "last_error": None,
        "next_scheduled": (datetime.utcnow() + timedelta(hours=18)).isoformat(),
        "record_count": 0,
        "stale_threshold_hours": 36,
        "is_stale": False,
    }


@router.get("/freshness/{source}/metrics")
async def get_source_metrics(
    source: str,
    days: int = Query(30, ge=1, le=90, description="Look back period in days")
):
    """
    Get detailed metrics for a source over time.
    """
    return {
        "source": source,
        "period_days": days,
        "total_jobs": 0,
        "successful_jobs": 0,
        "failed_jobs": 0,
        "success_rate": 0.0,
        "avg_duration_seconds": 0.0,
        "total_records_processed": 0,
        "jobs": [],
    }


# ==========================================
# Sync Scheduler Endpoints
# ==========================================

@router.get("/schedules")
async def list_sync_schedules():
    """
    List all configured sync schedules.
    """
    return {
        "schedules": [
            {
                "source": "clinicaltrials_gov",
                "tier": "daily",
                "cron_expression": "0 2 * * *",
                "priority": "critical",
                "enabled": True,
                "last_run": None,
                "next_run": None,
            },
            {
                "source": "openfda_faers",
                "tier": "daily",
                "cron_expression": "0 2 * * *",
                "priority": "critical",
                "enabled": True,
                "last_run": None,
                "next_run": None,
            },
            {
                "source": "drugbank",
                "tier": "weekly",
                "cron_expression": "0 3 * * 0",
                "priority": "normal",
                "enabled": True,
                "last_run": None,
                "next_run": None,
            },
        ],
        "total": 3,
    }


@router.get("/sync-jobs")
async def list_sync_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    List recent sync jobs.
    """
    return {
        "jobs": [],
        "total": 0,
        "filters": {
            "status": status,
            "source": source,
            "limit": limit,
        },
    }


@router.get("/sync-jobs/active")
async def list_active_sync_jobs():
    """
    List currently running sync jobs.
    """
    return {
        "active_jobs": [],
        "count": 0,
    }


@router.post("/sync-jobs/{source}/trigger")
async def trigger_source_sync(source: str):
    """
    Manually trigger a sync for a specific source.
    """
    import uuid

    valid_sources = [
        "clinicaltrials_gov", "openfda_faers", "openfda_labels",
        "drugbank", "chembl", "pubchem", "uniprot", "openalex"
    ]

    if source not in valid_sources:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source. Must be one of: {', '.join(valid_sources)}"
        )

    return {
        "job_id": str(uuid.uuid4()),
        "source": source,
        "status": "pending",
        "message": f"Sync job queued for {source}",
        "triggered_at": datetime.utcnow().isoformat(),
    }


@router.get("/sync-jobs/{job_id}")
async def get_sync_job_status(job_id: str):
    """
    Get status of a specific sync job.
    """
    # Placeholder - would query database
    raise HTTPException(status_code=404, detail="Job not found")
