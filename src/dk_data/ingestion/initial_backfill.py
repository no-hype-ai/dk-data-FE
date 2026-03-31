#!/usr/bin/env python3
"""Initial backfill entrypoint — fetches ALL external data + runs SQLMesh historical plan.

This is a ONE-TIME job run at platform initialization. It:

  1. Computes the historical fetch window automatically (from SQLMESH_START_DATE to today)
  2. Fetches EVERY registered source with the full historical window
  3. Skips sources that already have a recent last_successful_refresh (idempotent re-runs)
  4. After all fetches complete, runs `sqlmesh plan --auto-apply` to backfill all
     bronze → silver → gold models from SQLMESH_START_DATE to today
  5. Then runs `sqlmesh run` to process any remaining current-day intervals

Run via k8s Job (no activeDeadlineSeconds — allow as long as needed):
  kubectl apply -f k8s/apps/cronjobs/base/job-initial-backfill.yaml -n dk-data-prod
  kubectl logs -f job/initial-backfill -n dk-data-prod

Can also be re-run safely: sources with fresh last_successful_refresh are skipped.
Force re-fetch of a specific source: DELETE FROM meta.data_sources WHERE source_name='foo'
  and last_successful_refresh=NULL will force re-fetch on next backfill run.
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from .main import SOURCES, _meta_name, get_last_successful_refresh, run_ingestion
from .utils.database import init_connection_pool, close_connection_pool

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s — %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# The SQLMesh start date — all models backfill from this point.
# Set to match config.yaml model_defaults.start.
SQLMESH_START_DATE = date(2024, 1, 1)

# Sources that should be skipped during backfill (either deprecated, disabled,
# or handled by separate file-upload workflows).
SKIP_SOURCES = {
    'acc_tvc',         # Manual file upload — no automated fetcher available
    'cms_inpatient',   # Manual file upload — no automated fetcher available
    'cms_cost_reports',# Handled by fetch_all_years() inside fetcher; runs separately
}

# File-based sources (default_days_back=None) that support multi-year fetching
# via their fetcher's built-in logic. No days_back override needed.
FILE_BASED_SOURCES = {
    source for source, info in SOURCES.items()
    if info.get('default_days_back') is None and 'fetcher' in info
}

# How stale a prior refresh must be before we re-fetch during backfill.
# If last_successful_refresh is within this many hours, skip (already fresh).
SKIP_IF_REFRESHED_WITHIN_HOURS = 12

# Per-source kwargs to pass during backfill to override conservative defaults.
# These raise record caps for API sources whose defaults are tuned for daily incremental runs.
BACKFILL_SOURCE_KWARGS: dict = {
    # OpenFDA: default max_records=5000; raise to FDA hard limit for full backfill
    'openfda_labels': {'max_records': 25_000},
    # ClinicalTrials: default max_records=10000; raise for multi-year window
    'clinicaltrials': {'max_records': 50_000},
    # UniProt: increase to fetch beyond the first page (500 results default)
    'uniprot': {'max_results': 5_000},
    # PDB: increase from 500 default for broader drug-target coverage
    'pdb': {'max_results': 2_000},
    # EMA regulatory: days_back=None fetches full dataset (all ~2641 records)
    'ema_regulatory': {'days_back': None},
    # Cochrane: raise to get full historical review set
    'cochrane': {'max_records': 10_000, 'days_back': None},
    # KEGG: raise to fetch all ~12,000 drug entries (default 5000)
    'kegg_drug': {'max_entries': 15_000},
}


def compute_backfill_days() -> int:
    """Compute days_back needed to cover from SQLMESH_START_DATE to today."""
    today = date.today()
    delta = today - SQLMESH_START_DATE
    # +2 day buffer for timezone edge cases
    return delta.days + 2


def should_skip_source(source: str) -> tuple[bool, str]:
    """Check if a source should be skipped during backfill.

    Returns (should_skip, reason).
    """
    if source in SKIP_SOURCES:
        return True, "excluded from automated backfill"

    source_info = SOURCES.get(source, {})
    if source_info.get('requires_file') and not source_info.get('fetcher'):
        return True, "file-required source with no automated fetcher"

    # Check if recently refreshed (within SKIP_IF_REFRESHED_WITHIN_HOURS)
    meta_source = _meta_name(source)
    last_refresh = get_last_successful_refresh(meta_source)
    if last_refresh is not None:
        hours_ago = (datetime.now(timezone.utc) - last_refresh).total_seconds() / 3600
        if hours_ago < SKIP_IF_REFRESHED_WITHIN_HOURS:
            return True, f"already refreshed {hours_ago:.1f}h ago (< {SKIP_IF_REFRESHED_WITHIN_HOURS}h threshold)"

    return False, ""


def run_sqlmesh_backfill(sqlmesh_dir: str) -> bool:
    """Run sqlmesh plan --auto-apply to backfill all models from SQLMESH_START_DATE."""
    logger.info("=" * 60)
    logger.info("SQLMESH BACKFILL: Running full historical plan from %s", SQLMESH_START_DATE)
    logger.info("This transforms all raw data into bronze → silver → gold layers.")
    logger.info("Expected duration: 30 minutes to several hours.")
    logger.info("=" * 60)

    start = time.monotonic()
    try:
        result = subprocess.run(
            ['python', '-m', 'sqlmesh', '--path', sqlmesh_dir, 'plan', '--auto-apply'],
            capture_output=False,  # let stdout/stderr stream directly
            timeout=None,          # no timeout — allow as long as needed
        )
        elapsed = time.monotonic() - start
        if result.returncode == 0:
            logger.info("SQLMesh plan completed successfully in %.0fs", elapsed)
            return True
        else:
            logger.error("SQLMesh plan failed (exit %d) after %.0fs", result.returncode, elapsed)
            return False
    except Exception as e:
        logger.error("SQLMesh plan raised exception: %s", e)
        return False


def run_sqlmesh_run(sqlmesh_dir: str) -> bool:
    """Run sqlmesh run to process any current-day intervals after the backfill."""
    logger.info("Running sqlmesh run for current-day intervals...")
    try:
        result = subprocess.run(
            ['python', '-m', 'sqlmesh', '--path', sqlmesh_dir, 'run'],
            capture_output=False,
            timeout=3600,
        )
        if result.returncode == 0:
            logger.info("sqlmesh run completed successfully")
            return True
        else:
            logger.warning("sqlmesh run exited %d — may be OK if no pending intervals", result.returncode)
            return True  # non-fatal
    except Exception as e:
        logger.error("sqlmesh run raised exception: %s", e)
        return False


def run_fetch_backfill(data_dir: str, dry_run: bool = False) -> dict:
    """Fetch ALL sources with the full historical window.

    Returns dict of {source: status} for reporting.
    """
    days_back = compute_backfill_days()
    logger.info("=" * 60)
    logger.info("FETCH BACKFILL: %d sources, window = %d days (since %s)",
                len(SOURCES), days_back, SQLMESH_START_DATE)
    logger.info("=" * 60)

    results = {}
    skipped = []
    success = []
    failed = []

    sources_to_run = [s for s in SOURCES if s not in SKIP_SOURCES]

    for i, source in enumerate(sources_to_run, 1):
        logger.info("[%d/%d] Source: %s", i, len(sources_to_run), source)

        skip, reason = should_skip_source(source)
        if skip:
            logger.info("  SKIP: %s", reason)
            skipped.append(source)
            results[source] = f"skipped: {reason}"
            continue

        source_info = SOURCES[source]
        is_file_based = source in FILE_BASED_SOURCES
        effective_days_back = None if is_file_based else days_back

        if dry_run:
            logger.info("  DRY RUN: would fetch days_back=%s", effective_days_back)
            results[source] = "dry-run"
            continue

        try:
            extra_kwargs = BACKFILL_SOURCE_KWARGS.get(source, {})
            result = run_ingestion(
                source=source,
                data_dir=data_dir,
                days_back=effective_days_back,  # None = file-based full refresh
                **extra_kwargs,
            )
            status = result.get('status', 'unknown')
            records = result.get('records_inserted', result.get('records_fetched', 0))
            logger.info("  %s: %s (%s records)", source, status.upper(), records)
            results[source] = status
            if status in ('success', 'partial'):
                success.append(source)
            else:
                failed.append(source)
        except Exception as e:
            logger.error("  EXCEPTION for %s: %s", source, e)
            results[source] = f"exception: {e}"
            failed.append(source)

    logger.info("")
    logger.info("FETCH BACKFILL COMPLETE:")
    logger.info("  Succeeded: %d sources", len(success))
    logger.info("  Skipped:   %d sources", len(skipped))
    logger.info("  Failed:    %d sources", len(failed))
    if failed:
        logger.warning("  Failed sources: %s", ', '.join(failed))

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Initial full backfill: fetch all sources + SQLMesh historical plan',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full backfill (fetch + sqlmesh plan + sqlmesh run):
  python -m dk_data.ingestion.initial_backfill

  # Fetch only (no sqlmesh):
  python -m dk_data.ingestion.initial_backfill --fetch-only

  # SQLMesh backfill only (data already in raw tables):
  python -m dk_data.ingestion.initial_backfill --sqlmesh-only

  # Dry run to see what would be fetched:
  python -m dk_data.ingestion.initial_backfill --dry-run
        """
    )
    parser.add_argument('--fetch-only', action='store_true',
                        help='Only fetch data into raw tables, skip SQLMesh')
    parser.add_argument('--sqlmesh-only', action='store_true',
                        help='Only run SQLMesh plan (raw tables already populated)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be fetched without actually running')
    parser.add_argument('--data-dir', default='/tmp/data/raw',
                        help='Directory for fetcher temp file storage')
    parser.add_argument('--sqlmesh-dir', default='src/dk_data/sqlmesh',
                        help='Path to SQLMesh project directory')

    args = parser.parse_args()

    Path(args.data_dir).mkdir(parents=True, exist_ok=True)

    overall_start = time.monotonic()
    logger.info("=" * 60)
    logger.info("INITIAL BACKFILL — dk-data platform")
    logger.info("SQLMesh start date: %s", SQLMESH_START_DATE)
    logger.info("Fetch window: %d days", compute_backfill_days())
    logger.info("=" * 60)

    exit_code = 0

    if not args.sqlmesh_only:
        # Step 1: Fetch all sources
        init_connection_pool()
        try:
            fetch_results = run_fetch_backfill(args.data_dir, dry_run=args.dry_run)
            failed_sources = [s for s, status in fetch_results.items()
                              if str(status).startswith(('failed', 'exception'))]
            if failed_sources:
                logger.warning("%d sources failed during fetch — continuing to SQLMesh", len(failed_sources))
                exit_code = 1  # partial failure, but continue
        finally:
            close_connection_pool()

    if args.dry_run or args.fetch_only:
        logger.info("Stopping here (--dry-run or --fetch-only specified)")
        sys.exit(exit_code)

    # Step 2: SQLMesh historical backfill
    sqlmesh_ok = run_sqlmesh_backfill(args.sqlmesh_dir)
    if not sqlmesh_ok:
        logger.error("SQLMesh backfill FAILED — check logs above")
        sys.exit(2)

    # Step 3: SQLMesh run (current day)
    run_sqlmesh_run(args.sqlmesh_dir)

    elapsed = time.monotonic() - overall_start
    logger.info("=" * 60)
    logger.info("INITIAL BACKFILL COMPLETE in %.0f minutes", elapsed / 60)
    logger.info("=" * 60)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
