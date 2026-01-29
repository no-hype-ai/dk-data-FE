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

from job_runner import JobStatus, get_job_runner

# Import observability (must be before other imports that use logging)
try:
    from dk_data.observability import setup_telemetry, setup_logging, get_logger
    from dk_data.observability.metrics import get_metrics, get_metrics_content_type, HTTP_REQUESTS_TOTAL
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    import logging
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

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
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
    "database": os.getenv("POSTGRES_DB", "edwards_tavr"),
}

# FastAPI app
app = FastAPI(
    title="TAVR Job Trigger API",
    description="API for triggering and monitoring batch data jobs",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include additional routers
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
try:
    from api.routes import (
        data_platform_router,
        monitoring_router,
        data_sources_router,
        onboarding_router,
        alerts_router,
    )
    app.include_router(data_platform_router, prefix="/api/v1")
    app.include_router(monitoring_router, prefix="/api/v1")
    app.include_router(data_sources_router, prefix="/api/v1")
    app.include_router(onboarding_router, prefix="/api/v1")
    app.include_router(alerts_router, prefix="/api/v1")
    logger.info("Loaded additional API routers: data_platform, monitoring, data_sources, onboarding, alerts")
except ImportError as e:
    logger.warning(f"Could not load additional routers: {e}")


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


@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    Feature: 002-production-readiness
    Task: T060
    """
    if not OBSERVABILITY_AVAILABLE:
        raise HTTPException(status_code=501, detail="Observability not available")

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
