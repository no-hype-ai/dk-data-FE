"""
Pipeline Monitoring Service

Monitors data pipeline health, tracks runs, and exposes Prometheus metrics.

Part of DK Molecule Data Platform (012-dk-data-platform)
Refactored: 013-dk-data-observability — metrics imported from observability.metrics
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
from dataclasses import dataclass, field
from enum import Enum
import logging

# Import all metrics from canonical source (013-dk-data-observability)
from dk_data.observability.metrics import (
    DK_PIPELINE_RUNS_TOTAL as PIPELINE_RUNS_TOTAL,
    DK_PIPELINE_DURATION_SECONDS as PIPELINE_DURATION_SECONDS,
    DK_PIPELINE_RECORDS_PROCESSED as PIPELINE_RECORDS_PROCESSED,
    DK_PIPELINE_ERRORS as PIPELINE_ERRORS_TOTAL,
    DK_SOURCE_LAST_SYNC as SOURCE_LAST_SYNC,
    DK_SOURCE_RECORDS_TOTAL as SOURCE_RECORDS_TOTAL,
    DK_RESOLUTION_QUEUE_SIZE as RESOLUTION_QUEUE_SIZE,
    DK_RESOLUTION_SUCCESS_RATE as RESOLUTION_SUCCESS_RATE,
    DK_MOLECULES_TOTAL as MOLECULES_TOTAL,
    DK_MOLECULES_BY_STAGE as MOLECULES_BY_STAGE,
)

logger = logging.getLogger(__name__)


class PipelineLayer(str, Enum):
    """Pipeline layers."""
    RAW = "raw"
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class RunStatus(str, Enum):
    """Pipeline run status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PipelineRun:
    """Record of a pipeline run."""
    id: UUID
    layer: PipelineLayer
    source: str
    status: RunStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    records_input: int = 0
    records_output: int = 0
    records_error: int = 0
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    duration_seconds: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineHealth:
    """Pipeline health summary."""
    overall_status: str
    layers: Dict[str, Dict[str, Any]]
    sources: Dict[str, Dict[str, Any]]
    recent_errors: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    checked_at: datetime


@dataclass
class SourceStatus:
    """Status for a data source."""
    source_name: str
    is_healthy: bool
    last_sync: Optional[datetime]
    next_sync: Optional[datetime]
    record_count: Dict[str, int]  # by layer
    error_rate_24h: float
    avg_sync_duration: float


class PipelineMonitoringService:
    """
    Service for monitoring data pipeline health.

    Features:
    - Track pipeline runs across layers
    - Expose Prometheus metrics
    - Calculate health scores
    - Alert on issues
    """

    def __init__(self, db_pool):
        """
        Initialize pipeline monitoring service.

        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool

    async def start_run(
        self,
        layer: PipelineLayer,
        source: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> PipelineRun:
        """
        Start tracking a new pipeline run.

        Args:
            layer: Pipeline layer (raw, bronze, silver, gold)
            source: Data source name
            metadata: Optional run metadata

        Returns:
            PipelineRun record
        """
        run = PipelineRun(
            id=uuid4(),
            layer=layer,
            source=source,
            status=RunStatus.RUNNING,
            started_at=datetime.utcnow(),
            metadata=metadata or {},
        )

        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO platform.pipeline_runs (
                    id, layer, source, status, started_at, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6)
            """,
                run.id, layer.value, source, RunStatus.RUNNING.value,
                run.started_at, run.metadata
            )

        PIPELINE_RUNS_TOTAL.labels(
            layer=layer.value, source=source, status="started"
        ).inc()

        logger.info(f"Started pipeline run {run.id} for {layer.value}/{source}")
        return run

    async def complete_run(
        self,
        run_id: UUID,
        status: RunStatus,
        records_input: int = 0,
        records_output: int = 0,
        records_error: int = 0,
        error_message: Optional[str] = None,
        error_details: Optional[Dict[str, Any]] = None
    ) -> PipelineRun:
        """
        Complete a pipeline run.

        Args:
            run_id: Run UUID
            status: Final status
            records_input: Number of input records
            records_output: Number of output records
            records_error: Number of error records
            error_message: Error message if failed
            error_details: Detailed error info

        Returns:
            Updated PipelineRun
        """
        completed_at = datetime.utcnow()

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT layer, source, started_at FROM platform.pipeline_runs
                WHERE id = $1
            """, run_id)

            if not row:
                raise ValueError(f"Run {run_id} not found")

            duration = (completed_at - row['started_at']).total_seconds()

            await conn.execute("""
                UPDATE platform.pipeline_runs
                SET status = $2,
                    completed_at = $3,
                    records_input = $4,
                    records_output = $5,
                    records_error = $6,
                    error_message = $7,
                    error_details = $8,
                    duration_seconds = $9
                WHERE id = $1
            """,
                run_id, status.value, completed_at,
                records_input, records_output, records_error,
                error_message, error_details, duration
            )

        # Update metrics
        layer = row['layer']
        source = row['source']

        PIPELINE_RUNS_TOTAL.labels(
            layer=layer, source=source, status=status.value
        ).inc()

        PIPELINE_DURATION_SECONDS.labels(
            layer=layer, source=source
        ).observe(duration)

        PIPELINE_RECORDS_PROCESSED.labels(
            layer=layer, source=source
        ).inc(records_output)

        if status == RunStatus.FAILED:
            PIPELINE_ERRORS_TOTAL.labels(
                layer=layer, error_type="run_failed"
            ).inc()

        if status == RunStatus.SUCCESS:
            SOURCE_LAST_SYNC.labels(source=source).set(completed_at.timestamp())

        logger.info(
            f"Completed run {run_id}: {status.value}, "
            f"processed {records_output}/{records_input} records in {duration:.1f}s"
        )

        return PipelineRun(
            id=run_id,
            layer=PipelineLayer(layer),
            source=source,
            status=status,
            started_at=row['started_at'],
            completed_at=completed_at,
            records_input=records_input,
            records_output=records_output,
            records_error=records_error,
            error_message=error_message,
            error_details=error_details,
            duration_seconds=duration,
        )

    async def get_pipeline_health(self) -> PipelineHealth:
        """
        Get overall pipeline health status.

        Returns:
            PipelineHealth summary
        """
        async with self.db_pool.acquire() as conn:
            # Get layer status
            layer_stats = await conn.fetch("""
                SELECT
                    layer,
                    COUNT(*) FILTER (WHERE status = 'success') as success_count,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed_count,
                    COUNT(*) as total_count,
                    AVG(duration_seconds) as avg_duration,
                    MAX(completed_at) as last_run
                FROM platform.pipeline_runs
                WHERE started_at > NOW() - INTERVAL '24 hours'
                GROUP BY layer
            """)

            # Get source status
            source_stats = await conn.fetch("""
                SELECT
                    source,
                    COUNT(*) FILTER (WHERE status = 'success') as success_count,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed_count,
                    MAX(completed_at) as last_sync
                FROM platform.pipeline_runs
                WHERE started_at > NOW() - INTERVAL '24 hours'
                GROUP BY source
            """)

            # Get recent errors
            recent_errors = await conn.fetch("""
                SELECT id, layer, source, error_message, started_at
                FROM platform.pipeline_runs
                WHERE status = 'failed'
                AND started_at > NOW() - INTERVAL '24 hours'
                ORDER BY started_at DESC
                LIMIT 10
            """)

            # Get record counts
            molecule_count = await conn.fetchval(
                "SELECT COUNT(*) FROM silver.molecules WHERE needs_review = FALSE"
            ) or 0

            quarantine_count = await conn.fetchval(
                "SELECT COUNT(*) FROM silver.molecules WHERE needs_review = TRUE"
            ) or 0

            queue_count = await conn.fetchval(
                "SELECT COUNT(*) FROM silver.resolution_queue WHERE status = 'pending'"
            ) or 0

        # Build layer dict
        layers = {}
        for row in layer_stats:
            success_rate = row['success_count'] / row['total_count'] if row['total_count'] > 0 else 0
            layers[row['layer']] = {
                "success_count": row['success_count'],
                "failed_count": row['failed_count'],
                "success_rate": round(success_rate, 2),
                "avg_duration_seconds": round(row['avg_duration'] or 0, 1),
                "last_run": row['last_run'].isoformat() if row['last_run'] else None,
                "status": "healthy" if success_rate >= 0.9 else "degraded" if success_rate >= 0.5 else "unhealthy",
            }

        # Build source dict
        sources = {}
        for row in source_stats:
            success_rate = row['success_count'] / (row['success_count'] + row['failed_count']) if (row['success_count'] + row['failed_count']) > 0 else 0
            sources[row['source']] = {
                "success_count": row['success_count'],
                "failed_count": row['failed_count'],
                "success_rate": round(success_rate, 2),
                "last_sync": row['last_sync'].isoformat() if row['last_sync'] else None,
                "status": "healthy" if success_rate >= 0.9 else "degraded" if success_rate >= 0.5 else "unhealthy",
            }

        # Calculate overall status
        all_healthy = all(layer.get("status") == "healthy" for layer in layers.values())
        any_unhealthy = any(layer.get("status") == "unhealthy" for layer in layers.values())
        overall = "healthy" if all_healthy else "unhealthy" if any_unhealthy else "degraded"

        # Update Prometheus gauges
        MOLECULES_TOTAL.labels(status="published").set(molecule_count)
        MOLECULES_TOTAL.labels(status="quarantined").set(quarantine_count)
        RESOLUTION_QUEUE_SIZE.labels(priority="all").set(queue_count)

        return PipelineHealth(
            overall_status=overall,
            layers=layers,
            sources=sources,
            recent_errors=[
                {
                    "id": str(e['id']),
                    "layer": e['layer'],
                    "source": e['source'],
                    "error": e['error_message'],
                    "timestamp": e['started_at'].isoformat(),
                }
                for e in recent_errors
            ],
            metrics={
                "total_molecules": molecule_count,
                "quarantined_molecules": quarantine_count,
                "resolution_queue_size": queue_count,
            },
            checked_at=datetime.utcnow(),
        )

    async def get_source_status(self, source_name: str) -> SourceStatus:
        """
        Get detailed status for a data source.

        Args:
            source_name: Name of the data source

        Returns:
            SourceStatus with detailed metrics
        """
        async with self.db_pool.acquire() as conn:
            # Get recent runs
            runs = await conn.fetch("""
                SELECT status, completed_at, duration_seconds
                FROM platform.pipeline_runs
                WHERE source = $1
                AND started_at > NOW() - INTERVAL '24 hours'
            """, source_name)

            # Get last successful sync
            last_sync = await conn.fetchval("""
                SELECT MAX(completed_at) FROM platform.pipeline_runs
                WHERE source = $1 AND status = 'success'
            """, source_name)

            # Get record counts by layer
            raw_count = await conn.fetchval(
                f"SELECT COUNT(*) FROM raw.{source_name}"
            ) if source_name != "openfda_faers" else 0

        # Calculate metrics
        success_count = sum(1 for r in runs if r['status'] == 'success')
        total_count = len(runs)
        error_rate = 1 - (success_count / total_count) if total_count > 0 else 0

        durations = [r['duration_seconds'] for r in runs if r['duration_seconds']]
        avg_duration = sum(durations) / len(durations) if durations else 0

        return SourceStatus(
            source_name=source_name,
            is_healthy=error_rate < 0.1,
            last_sync=last_sync,
            next_sync=None,  # Would calculate from schedule
            record_count={"raw": raw_count or 0},
            error_rate_24h=round(error_rate, 3),
            avg_sync_duration=round(avg_duration, 1),
        )

    async def get_recent_runs(
        self,
        layer: Optional[PipelineLayer] = None,
        source: Optional[str] = None,
        status: Optional[RunStatus] = None,
        limit: int = 50
    ) -> List[PipelineRun]:
        """
        Get recent pipeline runs.

        Args:
            layer: Optional filter by layer
            source: Optional filter by source
            status: Optional filter by status
            limit: Maximum runs to return

        Returns:
            List of PipelineRun records
        """
        query = """
            SELECT * FROM platform.pipeline_runs
            WHERE 1=1
        """
        params = []
        param_idx = 1

        if layer:
            query += f" AND layer = ${param_idx}"
            params.append(layer.value)
            param_idx += 1

        if source:
            query += f" AND source = ${param_idx}"
            params.append(source)
            param_idx += 1

        if status:
            query += f" AND status = ${param_idx}"
            params.append(status.value)
            param_idx += 1

        query += f" ORDER BY started_at DESC LIMIT ${param_idx}"
        params.append(limit)

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [
            PipelineRun(
                id=r['id'],
                layer=PipelineLayer(r['layer']),
                source=r['source'],
                status=RunStatus(r['status']),
                started_at=r['started_at'],
                completed_at=r['completed_at'],
                records_input=r['records_input'] or 0,
                records_output=r['records_output'] or 0,
                records_error=r['records_error'] or 0,
                error_message=r['error_message'],
                error_details=r['error_details'],
                duration_seconds=r['duration_seconds'],
                metadata=r['metadata'] or {},
            )
            for r in rows
        ]

    async def update_metrics(self):
        """Update all Prometheus metrics from current data."""
        async with self.db_pool.acquire() as conn:
            # Update molecule counts by stage
            stage_counts = await conn.fetch("""
                SELECT development_status, COUNT(*) as count
                FROM silver.molecules
                WHERE needs_review = FALSE
                GROUP BY development_status
            """)

            for row in stage_counts:
                MOLECULES_BY_STAGE.labels(stage=row['development_status'] or 'unknown').set(row['count'])

            # Update resolution queue
            queue_counts = await conn.fetch("""
                SELECT
                    CASE
                        WHEN confidence_score >= 0.5 THEN 'high'
                        WHEN confidence_score >= 0.3 THEN 'medium'
                        ELSE 'low'
                    END as priority,
                    COUNT(*) as count
                FROM silver.resolution_queue
                WHERE status = 'pending'
                GROUP BY 1
            """)

            for row in queue_counts:
                RESOLUTION_QUEUE_SIZE.labels(priority=row['priority']).set(row['count'])

            # Update resolution success rate
            resolution_stats = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'approved') as approved,
                    COUNT(*) as total
                FROM silver.resolution_queue
                WHERE reviewed_at > NOW() - INTERVAL '30 days'
            """)

            if resolution_stats and resolution_stats['total'] > 0:
                rate = resolution_stats['approved'] / resolution_stats['total']
                RESOLUTION_SUCCESS_RATE.set(rate)

            # Update source record counts
            sources = ['clinicaltrials', 'openfda_labels', 'chembl', 'drugbank', 'pubchem']
            for source in sources:
                try:
                    count = await conn.fetchval(f"SELECT COUNT(*) FROM raw.{source}")
                    SOURCE_RECORDS_TOTAL.labels(source=source, layer='raw').set(count or 0)
                except Exception:
                    pass

        logger.info("Updated Prometheus metrics")
