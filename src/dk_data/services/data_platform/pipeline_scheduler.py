#!/usr/bin/env python3
"""
Pipeline Scheduler Service

A long-running service that orchestrates the data pipeline on scheduled intervals.
This runs as a separate Docker container and manages:
- Daily syncs (2 AM UTC): ClinicalTrials.gov, OpenFDA Labels
- Weekly syncs (Sunday 3 AM UTC): FAERS, DrugBank, ChEMBL
- Monthly syncs (1st 4 AM UTC): PubChem, UniProt

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import asyncio
import os
import signal
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PipelineScheduler:
    """
    Main scheduler service that runs the data pipeline on configured intervals.
    """

    # Schedules: (hour, minute, day_of_week or day_of_month)
    # day_of_week: 0=Monday, 6=Sunday, None=any
    # day_of_month: 1-31, None=any
    # All 16+ data sources organized by refresh frequency
    SCHEDULES = {
        'daily': {
            'sources': [
                'clinicaltrials',      # ClinicalTrials.gov - high update frequency
                'openfda_labels',      # FDA drug labels
                'dailymed',            # DailyMed labels
                'websearch',           # News/search results (on-demand cache refresh)
            ],
            'hour': 2,
            'minute': 0,
            'day_of_week': None,  # Every day
            'day_of_month': None,
        },
        'weekly': {
            'sources': [
                'openfda_faers',       # Adverse event reports
                'chembl',              # ChEMBL bioactivity
                'openalex',            # OpenAlex publications
                'rxnorm',              # RxNorm drug nomenclature
                'sider',               # Side effect data
                'who_inn',             # WHO INN names
            ],
            'hour': 3,
            'minute': 0,
            'day_of_week': 6,  # Sunday
            'day_of_month': None,
        },
        'monthly': {
            'sources': [
                'pubchem',             # PubChem compound data
                'uniprot',             # UniProt protein targets
                'drugbank',            # DrugBank comprehensive
                'kegg_drug',           # KEGG drug database
                'pharmgkb',            # PharmGKB pharmacogenomics
                'bindingdb',           # BindingDB binding affinity
                'tdc_admet',           # TDC ADMET predictions
            ],
            'hour': 4,
            'minute': 0,
            'day_of_week': None,
            'day_of_month': 1,  # First of month
        },
    }

    # Identifier linking schedules (run after main data syncs)
    LINKING_SCHEDULES = {
        'daily_linking': {
            'hour': 5,           # 5 AM UTC (after daily sync at 2 AM)
            'minute': 0,
            'batch_size': 100,
        },
        'weekly_linking': {
            'hour': 6,           # 6 AM UTC (after weekly sync at 3 AM)
            'minute': 0,
            'day_of_week': 6,    # Sunday
            'batch_size': 500,
        },
    }

    def __init__(self):
        self.running = False
        self.pool = None
        self.last_runs: Dict[str, datetime] = {}
        self.last_linking_runs: Dict[str, datetime] = {}
        self._shutdown_event = asyncio.Event()
        self._linker = None  # Lazy-loaded identifier linker

    async def load_last_runs_from_db(self):
        """Load last run times from database (persists across restarts)."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            # Load last_run from sync_schedules for each tier
            rows = await conn.fetch("""
                SELECT tier, MAX(last_run) as last_run
                FROM raw.sync_schedules
                WHERE last_run IS NOT NULL
                GROUP BY tier
            """)
            for row in rows:
                if row['last_run']:
                    self.last_runs[row['tier']] = row['last_run'].replace(tzinfo=None)
                    logger.info(f"Loaded last_run for {row['tier']}: {row['last_run']}")

            # Load last linking runs
            for linking_type in self.LINKING_SCHEDULES.keys():
                try:
                    last_run = await conn.fetchval("""
                        SELECT MAX(completed_at)
                        FROM raw.pipeline_jobs
                        WHERE job_type = $1 AND status = 'completed'
                    """, linking_type)
                    if last_run:
                        self.last_linking_runs[linking_type] = last_run.replace(tzinfo=None)
                        logger.info(f"Loaded last_run for {linking_type}: {last_run}")
                except Exception:
                    # Table may not exist yet
                    pass

    async def update_sync_schedules_after_run(self, tier: str, sources: List[str]):
        """Update sync_schedules table after a tier completes."""
        pool = await self.get_pool()
        now = datetime.utcnow()

        # Calculate next run based on schedule
        schedule = self.SCHEDULES.get(tier, {})
        next_run = self._calculate_next_run(tier, schedule)

        async with pool.acquire() as conn:
            for source in sources:
                await conn.execute("""
                    UPDATE raw.sync_schedules
                    SET last_run = $1, next_run = $2, updated_at = NOW()
                    WHERE source = $3
                """, now, next_run, source)
        logger.info(f"Updated sync_schedules for tier {tier}: last_run={now}, next_run={next_run}")

    def _calculate_next_run(self, tier: str, schedule: Dict) -> datetime:
        """Calculate next run time based on schedule configuration."""
        now = datetime.utcnow()

        if tier == 'daily':
            # Next day at scheduled time
            next_run = now.replace(
                hour=schedule.get('hour', 2),
                minute=schedule.get('minute', 0),
                second=0,
                microsecond=0
            )
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run

        elif tier == 'weekly':
            # Next occurrence of scheduled day
            target_dow = schedule.get('day_of_week', 6)  # Default Sunday
            days_ahead = target_dow - now.weekday()
            if days_ahead <= 0:  # Already past or is today
                days_ahead += 7
            next_run = now + timedelta(days=days_ahead)
            return next_run.replace(
                hour=schedule.get('hour', 3),
                minute=schedule.get('minute', 0),
                second=0,
                microsecond=0
            )

        elif tier == 'monthly':
            # First of next month
            if now.month == 12:
                next_run = now.replace(year=now.year + 1, month=1, day=1)
            else:
                next_run = now.replace(month=now.month + 1, day=1)
            return next_run.replace(
                hour=schedule.get('hour', 4),
                minute=schedule.get('minute', 0),
                second=0,
                microsecond=0
            )

        # Default: tomorrow
        return now + timedelta(days=1)

    async def initialize_sync_schedules(self):
        """Initialize next_run values for all schedules if not set."""
        pool = await self.get_pool()
        async with pool.acquire() as conn:
            for tier, schedule in self.SCHEDULES.items():
                next_run = self._calculate_next_run(tier, schedule)
                for source in schedule['sources']:
                    # Update next_run only if it's NULL
                    await conn.execute("""
                        UPDATE raw.sync_schedules
                        SET next_run = $1, updated_at = NOW()
                        WHERE source = $2 AND next_run IS NULL
                    """, next_run, source)
        logger.info("Initialized next_run values for schedules")

    async def get_pool(self):
        """Get or create database connection pool."""
        if self.pool is None:
            import asyncpg

            db_url = os.getenv('DATABASE_URL')
            if not db_url:
                db_host = os.getenv('POSTGRES_HOST', 'postgres')
                db_port = os.getenv('POSTGRES_PORT', '5432')
                db_name = os.getenv('POSTGRES_DB', 'dk_data')
                db_user = os.getenv('POSTGRES_USER', 'postgres')
                db_pass = os.getenv('POSTGRES_PASSWORD', 'postgres')
                db_url = f'postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}'

            self.pool = await asyncpg.create_pool(db_url, min_size=2, max_size=10)
            logger.info("Database connection pool created")

        return self.pool

    async def close(self):
        """Close resources."""
        if self._linker:
            await self._linker.close()
            self._linker = None
        if self.pool:
            await self.pool.close()
            self.pool = None

    def should_run_tier(self, tier: str, schedule: Dict) -> bool:
        """Check if a tier should run now."""
        now = datetime.utcnow()

        # Check if already ran today/this week/this month
        last_run = self.last_runs.get(tier)
        if last_run:
            if tier == 'daily' and last_run.date() == now.date():
                return False
            if tier == 'weekly' and (now - last_run) < timedelta(days=1):
                return False
            if tier == 'monthly' and last_run.month == now.month and last_run.year == now.year:
                return False

        # Check schedule
        if schedule.get('day_of_month') and now.day != schedule['day_of_month']:
            return False
        if schedule.get('day_of_week') is not None and now.weekday() != schedule['day_of_week']:
            return False
        if now.hour != schedule['hour']:
            return False
        if now.minute != schedule['minute']:
            return False

        return True

    async def run_tier(self, tier: str, sources: List[str]) -> Dict[str, Any]:
        """Run pipeline for a specific tier."""
        from .sync_runner import run_pipeline
        from .metrics import set_pipeline_active, record_pipeline_job

        logger.info(f"Starting {tier} pipeline for sources: {sources}")

        set_pipeline_active(tier, True)
        start_time = time.time()

        try:
            result = await run_pipeline(
                sources=sources,
                tier=tier,
                full_refresh=False,
                skip_raw=False,
                skip_bronze=False,
                skip_silver=False,
                skip_gold=False,
            )

            duration = time.time() - start_time
            status = 'completed' if result['status'] == 'completed' else 'failed'
            record_pipeline_job(tier, status, duration)

            self.last_runs[tier] = datetime.utcnow()

            # Update database with last_run and next_run
            await self.update_sync_schedules_after_run(tier, sources)

            logger.info(f"Completed {tier} pipeline in {duration:.2f}s: {result['status']}")

            return result

        except Exception as e:
            duration = time.time() - start_time
            record_pipeline_job(tier, 'failed', duration)
            logger.error(f"Failed {tier} pipeline: {e}")
            return {'status': 'failed', 'error': str(e)}

        finally:
            set_pipeline_active(tier, False)

    async def get_identifier_linker(self):
        """Get or create the identifier linker service."""
        if self._linker is None:
            from .identifier_linker import create_identifier_linker
            pool = await self.get_pool()
            self._linker = await create_identifier_linker(pool)
        return self._linker

    def should_run_linking(self, linking_type: str, schedule: Dict) -> bool:
        """Check if an identifier linking job should run now."""
        now = datetime.utcnow()

        # Check if already ran today
        last_run = self.last_linking_runs.get(linking_type)
        if last_run and last_run.date() == now.date():
            return False

        # Check day of week for weekly linking
        if schedule.get('day_of_week') is not None and now.weekday() != schedule['day_of_week']:
            return False

        # Check hour and minute
        if now.hour != schedule['hour']:
            return False
        if now.minute != schedule['minute']:
            return False

        return True

    async def record_linking_job(
        self,
        linking_type: str,
        status: str,
        duration: float,
        molecules_processed: int,
        identifiers_linked: int,
        errors: int
    ):
        """Record a linking job to the database for persistence."""
        try:
            pool = await self.get_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO raw.pipeline_jobs (
                        job_type, status, duration_seconds, completed_at,
                        molecules_processed, identifiers_linked, errors
                    ) VALUES ($1, $2, $3, NOW(), $4, $5, $6)
                """, linking_type, status, duration, molecules_processed, identifiers_linked, errors)
        except Exception as e:
            # Table may not exist, log but don't fail
            logger.warning(f"Could not record linking job: {e}")

    async def run_identifier_linking(self, linking_type: str, batch_size: int) -> Dict[str, Any]:
        """Run identifier linking job."""
        from .metrics import set_pipeline_active, record_pipeline_job

        logger.info(f"Starting {linking_type} identifier linking (batch_size={batch_size})")

        set_pipeline_active(linking_type, True)
        start_time = time.time()

        try:
            linker = await self.get_identifier_linker()

            if linking_type == 'daily_linking':
                result = await linker.run_daily_linking(batch_size=batch_size)
            else:
                result = await linker.run_weekly_linking(batch_size=batch_size)

            duration = time.time() - start_time
            status = 'completed' if len(result.errors) == 0 else 'partial'
            record_pipeline_job(linking_type, status, duration)

            self.last_linking_runs[linking_type] = datetime.utcnow()

            # Record to database for persistence
            await self.record_linking_job(
                linking_type, status, duration,
                result.molecules_processed, result.identifiers_linked, len(result.errors)
            )

            logger.info(
                f"Completed {linking_type}: processed={result.molecules_processed}, "
                f"linked={result.identifiers_linked}, duration={duration:.2f}s"
            )

            return {
                'status': status,
                'molecules_processed': result.molecules_processed,
                'identifiers_linked': result.identifiers_linked,
                'errors': len(result.errors),
                'duration': duration,
            }

        except Exception as e:
            duration = time.time() - start_time
            record_pipeline_job(linking_type, 'failed', duration)
            await self.record_linking_job(linking_type, 'failed', duration, 0, 0, 1)
            logger.error(f"Failed {linking_type}: {e}")
            return {'status': 'failed', 'error': str(e)}

        finally:
            set_pipeline_active(linking_type, False)

    async def check_and_run_schedules(self):
        """Check schedules and run due tiers and linking jobs."""
        # Run data sync tiers
        for tier, schedule in self.SCHEDULES.items():
            if self.should_run_tier(tier, schedule):
                try:
                    await self.run_tier(tier, schedule['sources'])
                except Exception as e:
                    logger.error(f"Error running {tier} schedule: {e}")

        # Run identifier linking jobs
        for linking_type, schedule in self.LINKING_SCHEDULES.items():
            if self.should_run_linking(linking_type, schedule):
                try:
                    await self.run_identifier_linking(
                        linking_type,
                        batch_size=schedule.get('batch_size', 100)
                    )
                except Exception as e:
                    logger.error(f"Error running {linking_type}: {e}")

    async def run_initial_sync(self):
        """Run initial sync to populate medallion layers from public schema."""
        logger.info("Running initial sync to populate medallion layers...")

        try:
            pool = await self.get_pool()

            # Check if bronze layer is empty
            async with pool.acquire() as conn:
                bronze_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM bronze.clinicaltrials
                """)

            if bronze_count == 0:
                logger.info("Bronze layer is empty, running initialization from public schema")

                # Import and run init from public
                from .sync_runner import run_pipeline

                # First, just run transformations (data is already in public)
                result = await run_pipeline(
                    sources=[],
                    tier='init',
                    full_refresh=True,
                    skip_raw=True,
                    skip_bronze=False,
                    skip_silver=False,
                    skip_gold=False,
                )

                logger.info(f"Initial sync completed: {result}")
            else:
                logger.info(f"Bronze layer already has {bronze_count} records, skipping initial sync")

        except Exception as e:
            logger.error(f"Initial sync failed: {e}")

    async def run(self):
        """Main scheduler loop."""
        self.running = True
        logger.info("Pipeline Scheduler started")
        logger.info(f"Data sync schedules: {list(self.SCHEDULES.keys())}")
        logger.info(f"Identifier linking schedules: {list(self.LINKING_SCHEDULES.keys())}")
        total_sources = sum(len(s['sources']) for s in self.SCHEDULES.values())
        logger.info(f"Total data sources configured: {total_sources}")

        # Wait for database to be ready
        for i in range(30):
            try:
                await self.get_pool()
                break
            except Exception:
                logger.warning(f"Waiting for database... ({i+1}/30)")
                await asyncio.sleep(2)

        # Load last_runs from database (persist across restarts)
        await self.load_last_runs_from_db()

        # Initialize next_run values if not set
        await self.initialize_sync_schedules()

        # Run initial sync if needed
        await self.run_initial_sync()

        # Main loop
        while self.running:
            try:
                await self.check_and_run_schedules()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")

            # Wait before next check (1 minute)
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=60)
                break  # Shutdown requested
            except asyncio.TimeoutError:
                pass  # Continue loop

        await self.close()
        logger.info("Pipeline Scheduler stopped")

    def stop(self):
        """Signal the scheduler to stop."""
        self.running = False
        self._shutdown_event.set()


async def main():
    """Entry point."""
    scheduler = PipelineScheduler()

    # Handle shutdown signals
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        scheduler.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Check if scheduler is enabled
    if os.getenv('SCHEDULER_ENABLED', 'true').lower() != 'true':
        logger.info("Scheduler is disabled, exiting")
        return

    await scheduler.run()


if __name__ == '__main__':
    asyncio.run(main())
