"""
Data Freshness Monitor

Monitors data source freshness and triggers refresh jobs based on tiered schedules.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
from enum import Enum
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class RefreshTier(str, Enum):
    """Data refresh tier."""
    DAILY = "daily"        # Critical sources: CT.gov, OpenFDA
    WEEKLY = "weekly"      # Reference sources: DrugBank, ChEMBL
    MONTHLY = "monthly"    # Stable sources: UniProt, PubChem
    ON_DEMAND = "on_demand"  # Manual refresh only


class SourceStatus(str, Enum):
    """Data source status."""
    HEALTHY = "healthy"
    STALE = "stale"
    ERROR = "error"
    REFRESHING = "refreshing"
    UNKNOWN = "unknown"


@dataclass
class SourceFreshness:
    """Freshness status for a data source."""
    source: str
    tier: RefreshTier
    status: SourceStatus
    last_refresh: Optional[datetime]
    last_success: Optional[datetime]
    last_error: Optional[str]
    next_scheduled: Optional[datetime]
    record_count: int
    stale_threshold_hours: int
    is_stale: bool


@dataclass
class FreshnessReport:
    """Overall data freshness report."""
    generated_at: datetime
    sources: List[SourceFreshness]
    healthy_count: int
    stale_count: int
    error_count: int
    overall_status: SourceStatus


class DataFreshnessMonitor:
    """
    Monitors data freshness across all sources.

    Tiered Refresh Schedule:
    - Daily: ClinicalTrials.gov, OpenFDA (FAERS, Labels)
    - Weekly: DrugBank, ChEMBL, OpenAlex
    - Monthly: UniProt, PubChem

    Features:
    - Tracks last refresh time per source
    - Detects stale data
    - Triggers scheduled refreshes
    - Provides freshness metrics
    """

    # Source configuration: tier and stale threshold (hours)
    SOURCE_CONFIG = {
        'clinicaltrials_gov': {
            'tier': RefreshTier.DAILY,
            'stale_hours': 36,  # Allow some buffer
            'display_name': 'ClinicalTrials.gov',
        },
        'openfda_faers': {
            'tier': RefreshTier.DAILY,
            'stale_hours': 36,
            'display_name': 'OpenFDA FAERS',
        },
        'openfda_labels': {
            'tier': RefreshTier.DAILY,
            'stale_hours': 36,
            'display_name': 'OpenFDA Drug Labels',
        },
        'drugbank': {
            'tier': RefreshTier.WEEKLY,
            'stale_hours': 192,  # 8 days
            'display_name': 'DrugBank',
        },
        'chembl': {
            'tier': RefreshTier.WEEKLY,
            'stale_hours': 192,
            'display_name': 'ChEMBL',
        },
        'openalex': {
            'tier': RefreshTier.WEEKLY,
            'stale_hours': 192,
            'display_name': 'OpenAlex',
        },
        'uniprot': {
            'tier': RefreshTier.MONTHLY,
            'stale_hours': 744,  # 31 days
            'display_name': 'UniProt',
        },
        'pubchem': {
            'tier': RefreshTier.MONTHLY,
            'stale_hours': 744,
            'display_name': 'PubChem',
        },
    }

    def __init__(self, db_pool, ingestion_service=None):
        """
        Initialize data freshness monitor.

        Args:
            db_pool: Database connection pool
            ingestion_service: Optional raw ingestion service for triggering refreshes
        """
        self.db_pool = db_pool
        self.ingestion_service = ingestion_service

    async def get_source_freshness(self, source: str) -> SourceFreshness:
        """Get freshness status for a specific source."""
        config = self.SOURCE_CONFIG.get(source, {
            'tier': RefreshTier.ON_DEMAND,
            'stale_hours': 720,
            'display_name': source,
        })

        async with self.db_pool.acquire() as conn:
            # Get refresh history
            history = await conn.fetchrow("""
                SELECT
                    MAX(completed_at) FILTER (WHERE status = 'completed') as last_success,
                    MAX(started_at) as last_refresh,
                    MAX(error_message) FILTER (WHERE status = 'failed') as last_error,
                    bool_or(status = 'processing') as is_refreshing
                FROM ops.ingestion_jobs
                WHERE source = $1
            """, source)

            # Get record count
            count = await conn.fetchval("""
                SELECT COUNT(*) FROM ops.api_responses
                WHERE source = $1
            """, source)

            last_success = history['last_success'] if history else None
            last_refresh = history['last_refresh'] if history else None
            last_error = history['last_error'] if history else None
            is_refreshing = history['is_refreshing'] if history else False

            # Calculate staleness
            stale_threshold = timedelta(hours=config['stale_hours'])
            is_stale = False
            if last_success:
                is_stale = datetime.utcnow() - last_success > stale_threshold
            else:
                is_stale = True  # Never refreshed = stale

            # Determine status
            if is_refreshing:
                status = SourceStatus.REFRESHING
            elif last_error and (not last_success or last_error > last_success):
                status = SourceStatus.ERROR
            elif is_stale:
                status = SourceStatus.STALE
            elif last_success:
                status = SourceStatus.HEALTHY
            else:
                status = SourceStatus.UNKNOWN

            # Calculate next scheduled refresh
            next_scheduled = None
            if last_success and config['tier'] != RefreshTier.ON_DEMAND:
                if config['tier'] == RefreshTier.DAILY:
                    next_scheduled = last_success + timedelta(days=1)
                elif config['tier'] == RefreshTier.WEEKLY:
                    next_scheduled = last_success + timedelta(days=7)
                elif config['tier'] == RefreshTier.MONTHLY:
                    next_scheduled = last_success + timedelta(days=30)

            return SourceFreshness(
                source=source,
                tier=config['tier'],
                status=status,
                last_refresh=last_refresh,
                last_success=last_success,
                last_error=last_error,
                next_scheduled=next_scheduled,
                record_count=count or 0,
                stale_threshold_hours=config['stale_hours'],
                is_stale=is_stale,
            )

    async def get_freshness_report(self) -> FreshnessReport:
        """Get overall freshness report for all sources."""
        sources = []
        for source in self.SOURCE_CONFIG.keys():
            freshness = await self.get_source_freshness(source)
            sources.append(freshness)

        healthy = sum(1 for s in sources if s.status == SourceStatus.HEALTHY)
        stale = sum(1 for s in sources if s.status == SourceStatus.STALE)
        error = sum(1 for s in sources if s.status == SourceStatus.ERROR)

        # Determine overall status
        if error > 0:
            overall = SourceStatus.ERROR
        elif stale > len(sources) / 2:
            overall = SourceStatus.STALE
        elif stale > 0:
            overall = SourceStatus.STALE  # Partial stale
        else:
            overall = SourceStatus.HEALTHY

        return FreshnessReport(
            generated_at=datetime.utcnow(),
            sources=sources,
            healthy_count=healthy,
            stale_count=stale,
            error_count=error,
            overall_status=overall,
        )

    async def get_stale_sources(self) -> List[str]:
        """Get list of stale sources that need refresh."""
        report = await self.get_freshness_report()
        return [s.source for s in report.sources if s.is_stale]

    async def check_and_trigger_refreshes(self) -> Dict[str, Any]:
        """
        Check for stale sources and trigger refreshes.

        Returns dict with triggered jobs.
        """
        if not self.ingestion_service:
            logger.warning("No ingestion service configured, cannot trigger refreshes")
            return {'triggered': [], 'skipped': []}

        stale_sources = await self.get_stale_sources()
        triggered = []
        skipped = []

        for source in stale_sources:
            config = self.SOURCE_CONFIG.get(source, {})
            if config.get('tier') == RefreshTier.ON_DEMAND:
                skipped.append({'source': source, 'reason': 'on_demand_only'})
                continue

            try:
                job_id = await self.ingestion_service.start_refresh(source)
                triggered.append({'source': source, 'job_id': str(job_id)})
                logger.info(f"Triggered refresh for stale source: {source}")
            except Exception as e:
                skipped.append({'source': source, 'reason': str(e)})
                logger.error(f"Failed to trigger refresh for {source}: {e}")

        return {
            'triggered': triggered,
            'skipped': skipped,
            'checked_at': datetime.utcnow().isoformat(),
        }

    async def get_source_metrics(self, source: str, days: int = 30) -> Dict[str, Any]:
        """Get detailed metrics for a source over time."""
        async with self.db_pool.acquire() as conn:
            # Get refresh history
            jobs = await conn.fetch("""
                SELECT status, started_at, completed_at, records_processed, error_message
                FROM ops.ingestion_jobs
                WHERE source = $1
                  AND started_at >= NOW() - ($2 || ' days')::interval
                ORDER BY started_at DESC
            """, source, days)

            # Calculate metrics
            total_jobs = len(jobs)
            successful = sum(1 for j in jobs if j['status'] == 'completed')
            failed = sum(1 for j in jobs if j['status'] == 'failed')

            # Average duration
            durations = []
            for job in jobs:
                if job['completed_at'] and job['started_at']:
                    duration = (job['completed_at'] - job['started_at']).total_seconds()
                    durations.append(duration)

            avg_duration = sum(durations) / len(durations) if durations else 0

            # Records processed
            total_records = sum(j['records_processed'] or 0 for j in jobs)

            return {
                'source': source,
                'period_days': days,
                'total_jobs': total_jobs,
                'successful_jobs': successful,
                'failed_jobs': failed,
                'success_rate': successful / total_jobs if total_jobs > 0 else 0,
                'avg_duration_seconds': avg_duration,
                'total_records_processed': total_records,
                'jobs': [dict(j) for j in jobs[:10]],  # Recent 10 jobs
            }

    async def record_refresh_start(self, source: str) -> UUID:
        """Record the start of a refresh job."""
        job_id = uuid4()
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO ops.ingestion_jobs (job_id, source, status, started_at)
                VALUES ($1, $2, 'processing', NOW())
            """, job_id, source)
        return job_id

    async def record_refresh_complete(
        self,
        job_id: UUID,
        success: bool,
        records_processed: int = 0,
        error_message: Optional[str] = None,
    ):
        """Record the completion of a refresh job."""
        status = 'completed' if success else 'failed'
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE ops.ingestion_jobs
                SET status = $2, completed_at = NOW(),
                    records_processed = $3, error_message = $4
                WHERE job_id = $1
            """, job_id, status, records_processed, error_message)
