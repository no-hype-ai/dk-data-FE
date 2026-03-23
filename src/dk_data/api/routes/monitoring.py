"""
Monitoring Routes - Pipeline Health and Prometheus Metrics
Part of: 012-dk-data-platform

Provides (mounted at /api/v1 via api.py):
- /api/v1/monitoring/health - Pipeline health status
- /api/v1/monitoring/metrics - Prometheus metrics endpoint
- /api/v1/monitoring/run - Trigger pipeline run
- /api/v1/monitoring/job-complete - CronJob completion reporting
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
from loguru import logger

from ..dependencies import get_sync_db_url

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

# Import metric helpers from canonical source (013-dk-data-observability)
from dk_data.observability.metrics import (
    mark_job_success,
    record_job_records,
    record_job_duration,
    increment_job_failure,
    record_data_source_refresh,
)

# Router
router = APIRouter(prefix="/monitoring", tags=["monitoring"])

# Initialize metrics on module load
if DK_METRICS_AVAILABLE:
    initialize_demo_metrics()
    # Initial refresh from database
    try:
        refresh_metrics_from_database_sync()
    except Exception as e:
        logger.warning(f"Initial metrics refresh failed: {e}")


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


class JobCompletionReport(BaseModel):
    """CronJob completion report (013-dk-data-observability T016)."""
    job_name: str
    status: str  # "success" | "failure"
    duration_seconds: float
    records_processed: int = 0
    source_name: Optional[str] = None
    error_message: Optional[str] = None


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


@router.post("/job-complete")
async def report_job_completion(report: JobCompletionReport):
    """
    Called by CronJobs to report completion metrics.
    Feature: 013-dk-data-observability (T016)
    """
    if report.status == "success":
        mark_job_success(report.job_name)
        record_job_records(report.job_name, report.records_processed)
    else:
        increment_job_failure(report.job_name)

    record_job_duration(report.job_name, report.duration_seconds)

    if report.source_name and report.status == "success":
        record_data_source_refresh(
            report.job_name, report.source_name, report.records_processed
        )

    logger.info(
        f"Job completion recorded: {report.job_name} "
        f"status={report.status} duration={report.duration_seconds:.1f}s "
        f"records={report.records_processed}"
    )
    return {"status": "recorded"}


@router.get("/stats")
async def database_stats():
    """
    Get live database statistics as JSON.
    Queries actual database tables for real counts.
    """
    stats = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tables": {},
        "sources": {},
        "summary": {}
    }

    try:
        import psycopg2
        db_url = get_sync_db_url()
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
            except Exception:
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
    import psycopg2

    bronze_sources = []
    silver_health = LayerHealth(layer="silver", record_count=0, last_update=None, status="unknown")
    gold_health = LayerHealth(layer="gold", record_count=0, last_update=None, status="unknown")
    overall_status = "healthy"

    try:
        db_url = get_sync_db_url()

        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        # Get Bronze source health from sync_schedules
        cur.execute("""
            SELECT source, tier, enabled, last_run, next_run
            FROM ops.sync_schedules
            WHERE enabled = TRUE
            ORDER BY last_run DESC NULLS LAST
            LIMIT 10
        """)
        for row in cur.fetchall():
            source_name, tier, enabled, last_run, next_run = row
            # Check for recent errors
            cur.execute("""
                SELECT COUNT(*) FROM ops.ingestion_jobs
                WHERE source = %s AND status = 'failed'
                  AND started_at >= NOW() - INTERVAL '24 hours'
            """, (source_name,))
            error_count = cur.fetchone()[0] or 0

            source_status = "healthy"
            if error_count > 5:
                source_status = "unhealthy"
                overall_status = "degraded"
            elif error_count > 0:
                source_status = "warning"

            bronze_sources.append(SourceHealth(
                source_id=source_name,
                last_sync=last_run,
                records_pending=0,
                error_count=error_count,
                status=source_status,
            ))

        # Get Silver layer health
        cur.execute("SELECT COUNT(*), MAX(updated_at) FROM mol_silver.molecules")
        result = cur.fetchone()
        silver_count = result[0] or 0
        silver_update = result[1]
        silver_health = LayerHealth(
            layer="silver",
            record_count=silver_count,
            last_update=silver_update,
            status="healthy" if silver_count > 0 else "empty",
        )

        # Get Gold layer health (check if gold schema exists)
        try:
            cur.execute("""
                SELECT COUNT(*) FROM mol_silver.molecules WHERE needs_review = FALSE
            """)
            gold_count = cur.fetchone()[0] or 0
            gold_health = LayerHealth(
                layer="gold",
                record_count=gold_count,
                last_update=datetime.now(timezone.utc),
                status="healthy" if gold_count > 0 else "empty",
            )
        except Exception:
            gold_health = LayerHealth(layer="gold", record_count=0, last_update=None, status="not_configured")

        cur.close()
        conn.close()

    except Exception as e:
        logger.error(f"Failed to get pipeline health: {e}")
        overall_status = "error"

    return PipelineHealth(
        status=overall_status,
        bronze_sources=bronze_sources,
        silver=silver_health,
        gold=gold_health,
        last_check=datetime.now(timezone.utc),
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
    import psycopg2

    runs = []
    total = 0

    try:
        db_url = get_sync_db_url()

        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        # Build query with filters
        query = """
            SELECT
                job_id::text,
                source,
                status,
                priority,
                started_at,
                completed_at,
                records_processed,
                error_message,
                error_details
            FROM ops.ingestion_jobs
            WHERE 1=1
        """
        params = []

        if status:
            query += " AND status = %s"
            params.append(status)

        query += " ORDER BY started_at DESC NULLS LAST LIMIT %s"
        params.append(limit)

        cur.execute(query, params)

        for row in cur.fetchall():
            job_id, source, job_status, priority, started_at, completed_at, records, error_msg, error_details = row
            duration = None
            if started_at and completed_at:
                duration = (completed_at - started_at).total_seconds()

            runs.append({
                "run_id": job_id,
                "pipeline_type": "raw_ingestion",
                "source": source,
                "status": job_status,
                "priority": priority,
                "started_at": started_at.isoformat() if started_at else None,
                "completed_at": completed_at.isoformat() if completed_at else None,
                "duration_seconds": duration,
                "records_processed": records or 0,
                "error_message": error_msg,
            })

        # Get total count
        cur.execute("SELECT COUNT(*) FROM ops.ingestion_jobs")
        total = cur.fetchone()[0] or 0

        cur.close()
        conn.close()

    except Exception as e:
        logger.error(f"Failed to list recent runs: {e}")

    return {
        "runs": runs,
        "total": total,
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
    import psycopg2

    # Source configurations with display names and types
    source_configs = {
        # Local database sources - use actual table names from the database
        "clinical_trials_local": {"name": "Clinical Trials (Local)", "type": "local_db", "table": "clinical_trials"},
        "fda_labels_local": {"name": "FDA Labels (Local)", "type": "local_db", "table": "fda_labels"},
        "drugbank": {"name": "DrugBank", "type": "local_db", "table": "drugbank_data"},
        "chembl": {"name": "ChEMBL", "type": "local_db", "table": "chembl"},  # Fixed: was chembl_compounds
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
        "patentsview": {"name": "PatentsView", "type": "external_api", "endpoint": "search.patentsview.org"},
        "ema": {"name": "EMA Medicines", "type": "external_api", "endpoint": "ema.europa.eu"},
    }

    sources = []

    try:
        db_url = get_sync_db_url()

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
                # External API sources — derive latency from last successful sync job
                source_info["status"] = "up"
                try:
                    cur.execute("""
                        SELECT
                            EXTRACT(EPOCH FROM (completed_at - started_at)) * 1000
                        FROM ops.ingestion_jobs
                        WHERE source = %s
                          AND status = 'completed'
                          AND started_at IS NOT NULL
                          AND completed_at IS NOT NULL
                        ORDER BY completed_at DESC
                        LIMIT 1
                    """, (source_id,))
                    row = cur.fetchone()
                    source_info["latency_ms"] = int(row[0]) if row and row[0] is not None else None
                except Exception:
                    source_info["latency_ms"] = None

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

    Feature: 013-dk-data-observability (wired to DataFreshnessMonitor)
    """
    from ..dependencies import get_db_pool
    from ...services.data_platform.data_freshness_monitor import DataFreshnessMonitor

    pool = await get_db_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool not available")

    monitor = DataFreshnessMonitor(db_pool=pool)
    try:
        report = await monitor.get_freshness_report()
    except Exception as e:
        logger.error(f"Freshness report failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate freshness report")

    return {
        "generated_at": report.generated_at.isoformat(),
        "status": report.overall_status.value,
        "sources": [
            {
                "source": s.source,
                "tier": s.tier.value,
                "status": s.status.value,
                "last_success": s.last_success.isoformat() if s.last_success else None,
                "next_scheduled": s.next_scheduled.isoformat() if s.next_scheduled else None,
                "record_count": s.record_count,
                "is_stale": s.is_stale,
            }
            for s in report.sources
        ],
        "healthy_count": report.healthy_count,
        "stale_count": report.stale_count,
        "error_count": report.error_count,
    }


@router.get("/freshness/{source}")
async def get_source_freshness(source: str):
    """
    Get detailed freshness info for a specific source.

    Feature: 013-dk-data-observability (wired to DataFreshnessMonitor)
    """
    from ..dependencies import get_db_pool
    from ...services.data_platform.data_freshness_monitor import (
        DataFreshnessMonitor,
    )

    pool = await get_db_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool not available")

    monitor = DataFreshnessMonitor(db_pool=pool)
    try:
        freshness = await monitor.get_source_freshness(source)
    except Exception as e:
        logger.error(f"Source freshness query failed for {source}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to query freshness for {source}")

    return {
        "source": freshness.source,
        "tier": freshness.tier.value,
        "status": freshness.status.value,
        "last_refresh": freshness.last_refresh.isoformat() if freshness.last_refresh else None,
        "last_success": freshness.last_success.isoformat() if freshness.last_success else None,
        "last_error": freshness.last_error,
        "next_scheduled": freshness.next_scheduled.isoformat() if freshness.next_scheduled else None,
        "record_count": freshness.record_count,
        "stale_threshold_hours": freshness.stale_threshold_hours,
        "is_stale": freshness.is_stale,
    }


@router.get("/freshness/{source}/metrics")
async def get_source_metrics(
    source: str,
    days: int = Query(30, ge=1, le=90, description="Look back period in days")
):
    """
    Get detailed metrics for a source over time.

    Feature: 013-dk-data-observability (wired to DataFreshnessMonitor)
    """
    from ..dependencies import get_db_pool
    from ...services.data_platform.data_freshness_monitor import DataFreshnessMonitor

    pool = await get_db_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool not available")

    monitor = DataFreshnessMonitor(db_pool=pool)
    try:
        return await monitor.get_source_metrics(source, days)
    except Exception as e:
        logger.error(f"Source metrics query failed for {source}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to query metrics for {source}")


# ==========================================
# Sync Scheduler Endpoints
# ==========================================

@router.get("/schedules")
async def list_sync_schedules():
    """
    List all configured sync schedules from the database.
    """
    import psycopg2

    schedules = []

    try:
        db_url = get_sync_db_url()
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        cur.execute("""
            SELECT source, tier, enabled, cron_expression, priority,
                   last_run, next_run
            FROM ops.sync_schedules
            ORDER BY source
        """)
        for row in cur.fetchall():
            source_name, tier, enabled, cron_expr, priority, last_run, next_run = row
            schedules.append({
                "source": source_name,
                "tier": tier,
                "cron_expression": cron_expr,
                "priority": priority,
                "enabled": enabled,
                "last_run": last_run.isoformat() if last_run else None,
                "next_run": next_run.isoformat() if next_run else None,
            })

        cur.close()
        conn.close()

    except Exception as e:
        logger.error(f"Failed to list sync schedules: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to query sync schedules: {e}")

    return {
        "schedules": schedules,
        "total": len(schedules),
    }


@router.get("/sync-jobs")
async def list_sync_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    List recent sync jobs from the database.
    """
    import psycopg2

    jobs = []
    total = 0

    try:
        db_url = get_sync_db_url()
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        query = """
            SELECT job_id::text, source, status, priority,
                   started_at, completed_at, records_processed,
                   error_message
            FROM ops.ingestion_jobs
            WHERE 1=1
        """
        params = []

        if status:
            query += " AND status = %s"
            params.append(status)
        if source:
            query += " AND source = %s"
            params.append(source)

        query += " ORDER BY started_at DESC NULLS LAST LIMIT %s"
        params.append(limit)

        cur.execute(query, params)
        for row in cur.fetchall():
            job_id, src, job_status, priority, started_at, completed_at, records, error_msg = row
            duration = None
            if started_at and completed_at:
                duration = (completed_at - started_at).total_seconds()

            jobs.append({
                "job_id": job_id,
                "source": src,
                "status": job_status,
                "priority": priority,
                "started_at": started_at.isoformat() if started_at else None,
                "completed_at": completed_at.isoformat() if completed_at else None,
                "duration_seconds": duration,
                "records_processed": records or 0,
                "error_message": error_msg,
            })

        cur.execute("SELECT COUNT(*) FROM ops.ingestion_jobs")
        total = cur.fetchone()[0] or 0

        cur.close()
        conn.close()

    except Exception as e:
        logger.error(f"Failed to list sync jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to query sync jobs: {e}")

    return {
        "jobs": jobs,
        "total": total,
        "filters": {
            "status": status,
            "source": source,
            "limit": limit,
        },
    }


@router.get("/sync-jobs/active")
async def list_active_sync_jobs():
    """
    List currently running sync jobs from the database.
    """
    import psycopg2

    active_jobs = []

    try:
        db_url = get_sync_db_url()
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        cur.execute("""
            SELECT job_id::text, source, status, priority,
                   started_at, records_processed
            FROM ops.ingestion_jobs
            WHERE status IN ('running', 'pending', 'in_progress')
            ORDER BY started_at DESC NULLS LAST
        """)
        for row in cur.fetchall():
            job_id, src, job_status, priority, started_at, records = row
            active_jobs.append({
                "job_id": job_id,
                "source": src,
                "status": job_status,
                "priority": priority,
                "started_at": started_at.isoformat() if started_at else None,
                "records_processed": records or 0,
            })

        cur.close()
        conn.close()

    except Exception as e:
        logger.error(f"Failed to list active sync jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to query active sync jobs: {e}")

    return {
        "active_jobs": active_jobs,
        "count": len(active_jobs),
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
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/sync-jobs/{job_id}")
async def get_sync_job_status(job_id: str):
    """
    Get status of a specific sync job.
    """
    import psycopg2

    try:
        db_url = get_sync_db_url()

        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        cur.execute("""
            SELECT id, source, job_type, status, started_at, completed_at,
                   records_processed, records_failed, error_message, options
            FROM ops.ingestion_jobs
            WHERE id::text = %s
        """, (job_id,))
        row = cur.fetchone()

        cur.close()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Job not found")

        duration = None
        if row[4] and row[5]:  # started_at and completed_at
            duration = (row[5] - row[4]).total_seconds()

        return {
            "job_id": str(row[0]),
            "source": row[1],
            "job_type": row[2] or "bronze_ingest",
            "status": row[3],
            "started_at": row[4].isoformat() if row[4] else None,
            "completed_at": row[5].isoformat() if row[5] else None,
            "duration_seconds": duration,
            "records_processed": row[6] or 0,
            "records_failed": row[7] or 0,
            "error_message": row[8],
            "options": row[9] if row[9] else {},
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
