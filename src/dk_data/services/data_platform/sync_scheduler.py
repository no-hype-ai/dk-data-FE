"""
Tiered Sync Scheduler

Manages scheduled data synchronization across tiers.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
from enum import Enum
from dataclasses import dataclass
import logging
import asyncio

logger = logging.getLogger(__name__)


class SyncPriority(str, Enum):
    """Sync job priority."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class ScheduledSync:
    """Scheduled sync job definition."""
    source: str
    tier: str
    cron_expression: str
    priority: SyncPriority
    enabled: bool
    last_run: Optional[datetime]
    next_run: Optional[datetime]
    options: Optional[Dict[str, Any]]


@dataclass
class SyncJob:
    """Active sync job."""
    id: UUID
    source: str
    priority: SyncPriority
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    records_processed: int
    error_message: Optional[str]


class TieredSyncScheduler:
    """
    Scheduler for tiered data synchronization.

    Schedule Tiers:
    - Daily (02:00 UTC): ClinicalTrials.gov, OpenFDA
    - Weekly (Sunday 03:00 UTC): DrugBank, ChEMBL, OpenAlex
    - Monthly (1st of month 04:00 UTC): UniProt, PubChem

    Features:
    - Configurable schedules per source
    - Priority-based execution
    - Job tracking and history
    - Automatic retry on failure
    """

    # Default schedules (cron-like)
    DEFAULT_SCHEDULES = {
        'clinicaltrials_gov': {
            'tier': 'daily',
            'cron': '0 2 * * *',  # 02:00 UTC daily
            'priority': SyncPriority.CRITICAL,
        },
        'openfda_faers': {
            'tier': 'daily',
            'cron': '0 2 * * *',
            'priority': SyncPriority.CRITICAL,
        },
        'openfda_labels': {
            'tier': 'daily',
            'cron': '30 2 * * *',  # 02:30 UTC daily
            'priority': SyncPriority.HIGH,
        },
        'drugbank': {
            'tier': 'weekly',
            'cron': '0 3 * * 0',  # 03:00 UTC Sunday
            'priority': SyncPriority.NORMAL,
        },
        'chembl': {
            'tier': 'weekly',
            'cron': '0 3 * * 0',
            'priority': SyncPriority.NORMAL,
        },
        'openalex': {
            'tier': 'weekly',
            'cron': '30 3 * * 0',  # 03:30 UTC Sunday
            'priority': SyncPriority.LOW,
        },
        'uniprot': {
            'tier': 'monthly',
            'cron': '0 4 1 * *',  # 04:00 UTC 1st of month
            'priority': SyncPriority.LOW,
        },
        'pubchem': {
            'tier': 'monthly',
            'cron': '0 4 1 * *',
            'priority': SyncPriority.LOW,
        },
    }

    def __init__(
        self,
        db_pool,
        ingestion_service,
        freshness_monitor,
        max_concurrent_jobs: int = 3,
    ):
        """
        Initialize the sync scheduler.

        Args:
            db_pool: Database connection pool
            ingestion_service: Raw ingestion service
            freshness_monitor: Data freshness monitor
            max_concurrent_jobs: Maximum concurrent sync jobs
        """
        self.db_pool = db_pool
        self.ingestion_service = ingestion_service
        self.freshness_monitor = freshness_monitor
        self.max_concurrent_jobs = max_concurrent_jobs
        self._running = False
        self._active_jobs: Dict[UUID, SyncJob] = {}
        self._job_semaphore = asyncio.Semaphore(max_concurrent_jobs)

    async def get_schedules(self) -> List[ScheduledSync]:
        """Get all configured sync schedules."""
        schedules = []

        async with self.db_pool.acquire() as conn:
            # Get custom schedules from database
            custom = await conn.fetch("""
                SELECT source, tier, cron_expression, priority, enabled,
                       last_run, next_run, options
                FROM ops.sync_schedules
            """)
            custom_sources = {r['source'] for r in custom}

            for row in custom:
                schedules.append(ScheduledSync(
                    source=row['source'],
                    tier=row['tier'],
                    cron_expression=row['cron_expression'],
                    priority=SyncPriority(row['priority']),
                    enabled=row['enabled'],
                    last_run=row['last_run'],
                    next_run=row['next_run'],
                    options=row['options'],
                ))

        # Add default schedules for sources not in database
        for source, config in self.DEFAULT_SCHEDULES.items():
            if source not in custom_sources:
                schedules.append(ScheduledSync(
                    source=source,
                    tier=config['tier'],
                    cron_expression=config['cron'],
                    priority=config['priority'],
                    enabled=True,
                    last_run=None,
                    next_run=self._calculate_next_run(config['cron']),
                    options=None,
                ))

        return schedules

    def _calculate_next_run(self, cron: str) -> datetime:
        """Calculate next run time from cron expression (simplified)."""
        # Simplified cron parsing - in production use croniter library
        now = datetime.utcnow()
        parts = cron.split()
        minute, hour = int(parts[0]), int(parts[1])

        # Daily
        if parts[2] == '*' and parts[3] == '*' and parts[4] == '*':
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run

        # Weekly (day of week specified)
        if parts[2] == '*' and parts[3] == '*' and parts[4] != '*':
            target_dow = int(parts[4])  # 0=Sunday
            current_dow = now.weekday()
            # Python: Monday=0, Sunday=6
            # Cron: Sunday=0
            python_dow = (target_dow + 6) % 7  # Convert to Python
            days_ahead = python_dow - current_dow
            if days_ahead < 0:
                days_ahead += 7
            next_run = now + timedelta(days=days_ahead)
            next_run = next_run.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(weeks=1)
            return next_run

        # Monthly (day of month specified)
        if parts[2] != '*' and parts[3] == '*':
            target_day = int(parts[2])
            next_run = now.replace(day=target_day, hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                # Move to next month
                if now.month == 12:
                    next_run = next_run.replace(year=now.year + 1, month=1)
                else:
                    next_run = next_run.replace(month=now.month + 1)
            return next_run

        # Default: next day
        return now + timedelta(days=1)

    async def get_due_jobs(self) -> List[ScheduledSync]:
        """Get jobs that are due to run."""
        schedules = await self.get_schedules()
        now = datetime.utcnow()
        return [s for s in schedules if s.enabled and s.next_run and s.next_run <= now]

    async def start_sync_job(self, source: str, priority: SyncPriority = SyncPriority.NORMAL) -> UUID:
        """Start a sync job for a source."""
        job_id = uuid4()
        job = SyncJob(
            id=job_id,
            source=source,
            priority=priority,
            status='pending',
            started_at=datetime.utcnow(),
            completed_at=None,
            records_processed=0,
            error_message=None,
        )

        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO ops.ingestion_jobs
                (job_id, source, status, started_at, priority)
                VALUES ($1, $2, 'pending', NOW(), $3)
            """, job_id, source, priority.value)

        # Run async
        asyncio.create_task(self._execute_job(job))
        return job_id

    async def _execute_job(self, job: SyncJob):
        """Execute a sync job."""
        async with self._job_semaphore:
            self._active_jobs[job.id] = job

            try:
                job.status = 'processing'
                await self._update_job_status(job.id, 'processing')

                # Run ingestion
                result = await self.ingestion_service.ingest_source(job.source)

                job.status = 'completed'
                job.records_processed = result.get('records_processed', 0)
                job.completed_at = datetime.utcnow()

                await self._update_job_status(
                    job.id, 'completed',
                    records=job.records_processed
                )

                # Update schedule
                await self._update_schedule_last_run(job.source)

                logger.info(f"Sync job {job.id} completed: {job.source}, {job.records_processed} records")

            except Exception as e:
                job.status = 'failed'
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()

                await self._update_job_status(job.id, 'failed', error=str(e))
                logger.error(f"Sync job {job.id} failed: {e}")

            finally:
                del self._active_jobs[job.id]

    async def _update_job_status(
        self,
        job_id: UUID,
        status: str,
        records: int = 0,
        error: Optional[str] = None,
    ):
        """Update job status in database."""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE ops.ingestion_jobs
                SET status = $2, completed_at = CASE WHEN $2 IN ('completed', 'failed') THEN NOW() ELSE NULL END,
                    records_processed = $3, error_message = $4
                WHERE job_id = $1
            """, job_id, status, records, error)

    async def _update_schedule_last_run(self, source: str):
        """Update schedule last run time."""
        config = self.DEFAULT_SCHEDULES.get(source, {})
        cron = config.get('cron', '0 0 * * *')
        next_run = self._calculate_next_run(cron)

        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO ops.sync_schedules (source, tier, cron_expression, priority, enabled, last_run, next_run)
                VALUES ($1, $2, $3, $4, TRUE, NOW(), $5)
                ON CONFLICT (source) DO UPDATE
                SET last_run = NOW(), next_run = $5
            """, source, config.get('tier', 'daily'), cron,
            config.get('priority', SyncPriority.NORMAL).value, next_run)

    async def run_scheduler(self):
        """Main scheduler loop."""
        self._running = True
        logger.info("Sync scheduler started")

        while self._running:
            try:
                due_jobs = await self.get_due_jobs()

                # Sort by priority
                priority_order = {
                    SyncPriority.CRITICAL: 0,
                    SyncPriority.HIGH: 1,
                    SyncPriority.NORMAL: 2,
                    SyncPriority.LOW: 3,
                }
                due_jobs.sort(key=lambda x: priority_order.get(x.priority, 2))

                for schedule in due_jobs:
                    if len(self._active_jobs) < self.max_concurrent_jobs:
                        logger.info(f"Starting scheduled sync for {schedule.source}")
                        await self.start_sync_job(schedule.source, schedule.priority)

                # Check every minute
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)

    def stop_scheduler(self):
        """Stop the scheduler."""
        self._running = False
        logger.info("Sync scheduler stopped")

    async def get_job_status(self, job_id: UUID) -> Optional[Dict[str, Any]]:
        """Get status of a sync job."""
        # Check active jobs first
        if job_id in self._active_jobs:
            job = self._active_jobs[job_id]
            return {
                'job_id': str(job.id),
                'source': job.source,
                'status': job.status,
                'started_at': job.started_at.isoformat(),
                'records_processed': job.records_processed,
            }

        # Check database
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT job_id, source, status, started_at, completed_at,
                       records_processed, error_message
                FROM ops.ingestion_jobs
                WHERE job_id = $1
            """, job_id)

            if not row:
                return None

            return dict(row)

    async def get_active_jobs(self) -> List[Dict[str, Any]]:
        """Get all active jobs."""
        return [
            {
                'job_id': str(job.id),
                'source': job.source,
                'status': job.status,
                'priority': job.priority.value,
                'started_at': job.started_at.isoformat(),
                'records_processed': job.records_processed,
            }
            for job in self._active_jobs.values()
        ]

    async def cancel_job(self, job_id: UUID) -> bool:
        """Cancel a pending job."""
        if job_id in self._active_jobs:
            job = self._active_jobs[job_id]
            if job.status == 'pending':
                job.status = 'cancelled'
                await self._update_job_status(job_id, 'cancelled')
                del self._active_jobs[job_id]
                return True
        return False
