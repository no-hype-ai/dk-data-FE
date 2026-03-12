"""
Job Trigger API
Feature: 002-production-readiness
Tasks: T044, T059, T060

FastAPI service for triggering and monitoring batch jobs.
Includes OpenTelemetry instrumentation and Prometheus metrics.
"""

import os
from datetime import datetime
from typing import Any

import psycopg2
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from dk_data.ingestion.batch.job_runner import JobStatus, get_job_runner

# Import observability (must be before other imports that use logging)
try:
    from dk_data.observability import setup_telemetry, setup_logging, get_logger
    from dk_data.observability.metrics import get_metrics, get_metrics_content_type
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    import logging
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

# FastAPI auto-instrumentation (013-dk-data-observability T022)
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    FASTAPI_INSTRUMENTOR_AVAILABLE = True
except ImportError:
    FASTAPI_INSTRUMENTOR_AVAILABLE = False

# Initialize observability
if OBSERVABILITY_AVAILABLE:
    setup_telemetry("job-trigger")
    setup_logging("job-trigger")
    logger = get_logger(__name__)
else:
    import logging
    logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "database": os.getenv("POSTGRES_DB", "dk_data"),
}

# FastAPI app
app = FastAPI(
    title="DK Data Platform API",
    description="API for triggering and monitoring batch data jobs (TAVR + Molecule Platform)",
    version="2.0.0",
)

# Auto-instrument FastAPI with OTel (013-dk-data-observability T022)
if OBSERVABILITY_AVAILABLE and FASTAPI_INSTRUMENTOR_AVAILABLE:
    FastAPIInstrumentor.instrument_app(app)
    logger.info("FastAPI auto-instrumented with OpenTelemetry")

# Molecule platform routers (004-molecule-platform-integration)
# Try/except pattern for graceful degradation if molecule modules unavailable
try:
    from dk_data.api.routes.data_platform import router as data_platform_router
    app.include_router(data_platform_router, prefix="/api/v1", tags=["molecule-platform"])
    logger.info("Loaded molecule data_platform router")
except ImportError as e:
    logger.warning(f"Molecule data_platform router not available: {e}")

try:
    from dk_data.api.routes.monitoring import router as monitoring_router
    app.include_router(monitoring_router, prefix="/api/v1", tags=["molecule-monitoring"])
    logger.info("Loaded molecule monitoring router")
except ImportError as e:
    logger.warning(f"Molecule monitoring router not available: {e}")

try:
    from dk_data.api.routes.data_sources import router as data_sources_router
    app.include_router(data_sources_router, prefix="/api/v1", tags=["molecule-data-sources"])
    logger.info("Loaded molecule data_sources router")
except ImportError as e:
    logger.warning(f"Molecule data_sources router not available: {e}")

try:
    from dk_data.api.routes.onboarding import router as onboarding_router
    app.include_router(onboarding_router, prefix="/api/v1", tags=["molecule-onboarding"])
    logger.info("Loaded molecule onboarding router")
except ImportError as e:
    logger.warning(f"Molecule onboarding router not available: {e}")

try:
    from dk_data.api.routes.alerts import router as alerts_router
    app.include_router(alerts_router, prefix="/api/v1", tags=["molecule-alerts"])
    logger.info("Loaded molecule alerts router")
except ImportError as e:
    logger.warning(f"Molecule alerts router not available: {e}")

# Unified data tools gateway router (replaces MCP tools router)
try:
    from dk_data.api.routes.data_tools import router as data_tools_router
    app.include_router(data_tools_router, prefix="/api/v1", tags=["data-tools"])
    logger.info("Loaded data tools gateway router")
except ImportError as e:
    logger.warning(f"Data tools router not available: {e}")

# Agent trigger + quarantine router (016-cms-puf-datasource-integration T085/T088)
try:
    from dk_data.api.routes.agents import router as agents_router
    app.include_router(agents_router, prefix="/api/v1", tags=["agents"])
    logger.info("Loaded agents router")
except ImportError as e:
    logger.warning(f"Agents router not available: {e}")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Audit logging middleware (013-observability-governance, US3: Audit Trail)
try:
    from dk_data.api.middleware import AuditLoggingMiddleware, RequestTrackingMiddleware, CacheControlMiddleware

    # Order: RequestTracking (outer) -> AuditLogging -> CacheControl (inner)
    app.add_middleware(RequestTrackingMiddleware)
    app.add_middleware(AuditLoggingMiddleware)
    app.add_middleware(CacheControlMiddleware)
    logger.info("Audit logging middleware registered")
except ImportError as e:
    logger.warning(f"Audit logging middleware not available: {e}")


# ─── Audit log archival (weekly: move hot→cold after 365 days) ────────────────
# Per FDA 21 CFR Part 11 & ICH E6(R3): audit data is NEVER deleted within the
# regulatory retention period (min 2 years, up to 7-25 years).
# This task only moves old rows from the fast hot table to the compressed archive.
@app.on_event("startup")
async def _schedule_audit_archive():
    """Archive old audit log entries weekly via background loop."""
    import asyncio
    from dk_data.api.dependencies import get_db_pool

    async def _archive_loop():
        await asyncio.sleep(60)  # wait for db pool init
        while True:
            try:
                pool = await get_db_pool()
                async with pool.acquire() as conn:
                    archived = await conn.fetchval("SELECT meta.archive_old_audit_logs(365)")
                    if archived and archived > 0:
                        logger.info(f"Audit log archival: moved {archived} rows older than 365 days to archive")
            except Exception as e:
                logger.debug(f"Audit log archival skipped: {e}")
            await asyncio.sleep(604800)  # 7 days

    asyncio.create_task(_archive_loop())


# Pydantic models
class JobInfo(BaseModel):
    job_id: int
    job_name: str
    description: str | None
    cron_schedule: str | None
    is_enabled: bool
    last_run_at: datetime | None
    last_run_status: str | None
    source_names: list[str]


class JobRunInfo(BaseModel):
    run_id: int
    job_name: str
    triggered_by: str
    triggered_by_user: str | None
    started_at: datetime
    completed_at: datetime | None
    status: str
    records_processed: int | None
    error_message: str | None
    k8s_job_name: str | None


class TriggerResponse(BaseModel):
    run_id: int | None
    job_name: str
    status: str
    message: str
    k8s_job_name: str | None = None


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    database: str
    version: str


def get_connection():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "disconnected"

    return HealthResponse(
        status="healthy" if db_status == "connected" else "degraded",
        timestamp=datetime.now(),
        database=db_status,
        version="1.0.0",
    )


@app.post("/cms/gold/refresh")
async def refresh_cms_gold():
    """Trigger CMS gold view refresh via SQLMesh.

    Feature: 016-cms-puf-datasource-integration (T102)
    """
    import subprocess
    try:
        result = subprocess.run(
            ["python", "-m", "sqlmesh", "plan", "--auto-apply", "--no-prompts"],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"SQLMesh refresh failed: {result.stderr[:500]}",
            )
        return {
            "status": "success",
            "message": "CMS gold views refreshed",
            "timestamp": datetime.now().isoformat(),
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Gold refresh timed out after 600s")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Gold refresh failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    Feature: 002-production-readiness
    Task: T060
    Updated: 013-dk-data-observability — refresh DB gauges before scrape
    """
    if not OBSERVABILITY_AVAILABLE:
        raise HTTPException(status_code=501, detail="Observability not available")

    # Refresh DB-backed gauges so Prometheus gets current values
    try:
        from dk_data.services.data_platform.metrics import refresh_metrics_from_database_sync
        refresh_metrics_from_database_sync()
    except Exception as e:
        logger.warning(f"Failed to refresh DB metrics before scrape: {e}")

    return Response(
        content=get_metrics(),
        media_type=get_metrics_content_type(),
    )


@app.get("/jobs", response_model=list[JobInfo])
async def list_jobs(
    enabled_only: bool = Query(False, description="Only return enabled jobs"),
):
    """List all available batch jobs."""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT
                bj.job_id,
                bj.job_name,
                bj.description,
                bj.cron_schedule,
                bj.is_enabled,
                bj.last_run_at,
                bj.last_run_status,
                COALESCE(
                    (SELECT ARRAY_AGG(ds.source_name)
                     FROM meta.data_sources ds
                     WHERE ds.source_id = ANY(bj.source_ids)),
                    '{}'::TEXT[]
                ) AS source_names
            FROM meta.batch_jobs bj
        """

        if enabled_only:
            query += " WHERE bj.is_enabled = TRUE"

        query += " ORDER BY bj.job_name"

        cursor.execute(query)
        jobs = cursor.fetchall()
        cursor.close()
        conn.close()

        return [JobInfo(**job) for job in jobs]

    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_name}", response_model=JobInfo)
async def get_job(job_name: str):
    """Get details of a specific job."""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                bj.job_id,
                bj.job_name,
                bj.description,
                bj.cron_schedule,
                bj.is_enabled,
                bj.last_run_at,
                bj.last_run_status,
                COALESCE(
                    (SELECT ARRAY_AGG(ds.source_name)
                     FROM meta.data_sources ds
                     WHERE ds.source_id = ANY(bj.source_ids)),
                    '{}'::TEXT[]
                ) AS source_names
            FROM meta.batch_jobs bj
            WHERE bj.job_name = %s
        """, (job_name,))

        job = cursor.fetchone()
        cursor.close()
        conn.close()

        if not job:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_name}")

        return JobInfo(**job)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job {job_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/jobs/{job_name}/trigger", response_model=TriggerResponse)
async def trigger_job(
    job_name: str,
    user: str | None = Query(None, description="User triggering the job"),
):
    """Trigger a batch job execution."""
    try:
        # Verify job exists and is enabled
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT job_id, is_enabled
            FROM meta.batch_jobs
            WHERE job_name = %s
        """, (job_name,))

        job = cursor.fetchone()
        cursor.close()
        conn.close()

        if not job:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_name}")

        if not job["is_enabled"]:
            raise HTTPException(status_code=400, detail=f"Job is disabled: {job_name}")

        # Get job runner and execute
        runner = get_job_runner(DB_CONFIG)
        result = runner.run_job(job_name, triggered_by="api", user=user)

        if result.status == JobStatus.FAILURE and result.run_id is None:
            raise HTTPException(status_code=500, detail=result.error_message)

        return TriggerResponse(
            run_id=result.run_id,
            job_name=result.job_name,
            status=result.status.value,
            message=f"Job {job_name} {'triggered successfully' if result.status != JobStatus.FAILURE else 'failed'}",
            k8s_job_name=result.k8s_job_name,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering job {job_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runs", response_model=list[JobRunInfo])
async def list_runs(
    job_name: str | None = Query(None, description="Filter by job name"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, description="Maximum number of runs to return"),
):
    """List job execution history."""
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT
                bjr.run_id,
                bj.job_name,
                bjr.triggered_by,
                bjr.triggered_by_user,
                bjr.started_at,
                bjr.completed_at,
                bjr.status,
                bjr.records_processed,
                bjr.error_message,
                bjr.k8s_job_name
            FROM meta.batch_job_runs bjr
            JOIN meta.batch_jobs bj ON bjr.job_id = bj.job_id
            WHERE 1=1
        """
        params: list[Any] = []

        if job_name:
            query += " AND bj.job_name = %s"
            params.append(job_name)

        if status:
            query += " AND bjr.status = %s"
            params.append(status)

        query += " ORDER BY bjr.started_at DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        runs = cursor.fetchall()
        cursor.close()
        conn.close()

        return [JobRunInfo(**run) for run in runs]

    except Exception as e:
        logger.error(f"Error listing runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runs/{run_id}", response_model=JobRunInfo)
async def get_run(run_id: int):
    """Get details of a specific job run."""
    try:
        runner = get_job_runner(DB_CONFIG)
        result = runner.get_job_status(run_id)

        if not result:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

        return JobRunInfo(
            run_id=result.run_id,
            job_name=result.job_name,
            triggered_by="unknown",  # Not stored in JobResult
            triggered_by_user=None,
            started_at=result.started_at,
            completed_at=result.completed_at,
            status=result.status.value,
            records_processed=result.records_processed,
            error_message=result.error_message,
            k8s_job_name=result.k8s_job_name,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting run {run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
