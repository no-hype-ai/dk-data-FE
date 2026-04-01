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

Parallelism (--workers N):
  Sources are split into three tiers by expected duration and API behaviour:

  HEAVY   — run sequentially after all light/medium sources finish.
            These are 2M-20M record fetches that each need several hours and
            significant memory. Running them concurrently would exhaust the
            pod's 8Gi memory limit.

  API_RATE_GROUPS — sources sharing an upstream host get a per-group semaphore
            capping how many can run simultaneously (default 2 for CMS, 1 for
            OpenFDA). Prevents rate-limit 429s without sacrificing throughput
            on other groups.

  LIGHT   — everything else. Runs up to --workers concurrent fetches.

  Recommended --workers values:
    1  (default)  — sequential, backward-compatible
    4             — safe for the 4 vCPU / 8 Gi pod spec; cuts wall-clock ~4x
    6             — max before connection pool pressure becomes noticeable
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Semaphore

from .main import SOURCES, _meta_name, get_last_successful_refresh, run_ingestion
from .utils.database import init_connection_pool, close_connection_pool

try:
    from prometheus_client import start_http_server
    from dk_data.observability.metrics import (
        record_job_duration,
        record_job_records,
        increment_job_failure,
        mark_job_success,
    )
    _METRICS_AVAILABLE = True
except ImportError:
    _METRICS_AVAILABLE = False
    def record_job_duration(job_name, duration_seconds): pass
    def record_job_records(job_name, count): pass
    def increment_job_failure(job_name): pass
    def mark_job_success(job_name): pass
    def start_http_server(port): pass

try:
    from dk_data.observability import setup_telemetry, setup_logging
    _OBSERVABILITY_AVAILABLE = True
except ImportError:
    _OBSERVABILITY_AVAILABLE = False
    def setup_telemetry(service_name, **kwargs): pass
    def setup_logging(service_name, **kwargs): pass

METRICS_PORT = 8000  # matches job-initial-backfill.yaml containerPort

# Minimal fallback logging for module-level code (before main() runs setup_logging).
# setup_logging() in main() will reconfigure structlog for JSON + trace-context injection.
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
    'acc_tvc',          # Manual file upload — no automated fetcher available
    'cms_inpatient',    # Manual file upload — no automated fetcher available
    'cms_cost_reports', # Handled by fetch_all_years() inside fetcher; runs separately
}

# Sources with no days_back window — full-corpus or file-based fetches that own
# their own pagination/year logic. Includes API sources (uniprot, drugbank, pdb,
# orcid) as well as file-download sources. No days_back override is applied.
TIMELESS_SOURCES = {
    source for source, info in SOURCES.items()
    if info.get('default_days_back') is None and 'fetcher' in info
}

# How stale a prior refresh must be before we re-fetch during backfill.
# If last_successful_refresh is within this many hours, skip (already fresh).
SKIP_IF_REFRESHED_WITHIN_HOURS = 12

# ---------------------------------------------------------------------------
# Parallelism tiers
# ---------------------------------------------------------------------------

# Sources that run sequentially AFTER the parallel batch completes.
# Each is a multi-hour, multi-GB fetch; running them concurrently would
# exhaust pod memory and thrash the DB writer.
HEAVY_SOURCES = {
    'chembl_molecules',    # ~2.4M compounds, 4h+
    'chembl_activities',   # ~17-20M bioactivity records, 5-6h
    'pubchem',             # ~2M compounds, 6h+
    'openfda_faers',       # full_backfill year-partitioned, 3-4h
    'npi_registry',        # ~7M providers, 3h+
}

# Sources sharing an upstream host — per-group semaphore caps concurrency.
# Key: semaphore limit (max concurrent fetches to that host).
# Value: set of source names hitting that host.
API_RATE_GROUPS: dict[str, tuple[int, set[str]]] = {
    # data.cms.gov throttles hard above ~3 concurrent clients.
    # Use 2 to leave headroom for other pods/CronJobs.
    'cms': (2, {s for s in SOURCES if s.startswith('cms_') and SOURCES[s].get('enabled', True)} - HEAVY_SOURCES),
    # openFDA (api.fda.gov) — 240 req/min authenticated, 40/min anon.
    # 1 concurrent is safest given year-partitioned loops.
    'openfda': (1, {'openfda_labels', 'fda_drugs', 'fda_ndc', 'fda_rems', 'purple_book'}),
    # ebi.ac.uk (ChEMBL REST, EuropePMC) — polite pool; 2 concurrent fine.
    'ebi': (2, {'europepmc'}),
}

# Per-source kwargs to pass during backfill to override conservative defaults.
# These raise record caps for API sources whose defaults are tuned for daily incremental runs.
BACKFILL_SOURCE_KWARGS: dict = {
    # OpenFDA Labels: full backfill via year-by-year partitioning (2000→present).
    # The FDA API caps skip at 25k per query; ~170-200k total SPL documents.
    # full_backfill=True iterates effective_time:[YEAR0101 TO YEAR1231] per year
    # (<25k per year on average) to retrieve all labels. Duplicates across years
    # (re-issued labels) are deduplicated at the bronze layer by set_id.
    'openfda_labels': {'full_backfill': True},
    # ClinicalTrials: default max_records=10000; raise for multi-year window
    'clinicaltrials': {'max_records': 50_000},
    # UniProt: broaden query from kinases-only to all reviewed human proteins
    # (DEFAULT_QUERY filters to GO:0004672 kinase activity only — ~500 proteins).
    # "reviewed:true AND organism_id:9606" covers all Swiss-Prot human entries (~20k).
    # Raise cap to match full dataset.
    'uniprot': {
        'query': 'reviewed:true AND organism_id:9606',
        'max_results': 25_000,
    },
    # PDB: raise to 50k — covers all drug-target-relevant crystal structures.
    # The fetcher paginates via RCSB paginate.start offset (500 entries/page) and
    # loops until the final page returns fewer than 500 results.
    'pdb': {'max_results': 50_000},
    # EMA regulatory: days_back=None fetches full dataset (all ~2641 records)
    'ema_regulatory': {'days_back': None},
    # Cochrane: raise to get full historical review set
    'cochrane': {'max_records': 10_000, 'days_back': None},
    # KEGG: raise to fetch all ~12,000 drug entries (default 5000)
    'kegg_drug': {'max_entries': 15_000},
    # ---------------------------------------------------------------------------
    # Incremental API sources — raise max_records for a 457-day backfill window.
    # The orchestrator already passes days_back=compute_backfill_days()≈457 to
    # every API source; without raised caps the fetchers hit their per-run
    # defaults (5k-10k) and miss historical records.
    # ---------------------------------------------------------------------------
    # ChEMBL activities: remove 500k safety cap — fetch all ~17-20M bioactivity records.
    # Paginated at 1000/req with 1s delay → ~5-6 hours. One-time cost for complete coverage.
    # Set to None: the fetcher's `if max_records and count >= max_records` check is falsy.
    'chembl_activities': {'max_records': None},
    # Literature
    'pubmed': {'max_records': 50_000},          # default: 10k; 457-day drug query can exceed that
    'europepmc': {'max_records': 50_000},        # default: 10k
    # Regulatory / CI (full-history fetches)
    'hta_bodies': {'days_back': None},           # default: 90 days; fetch full NICE TA archive
    'openalex_ci': {'max_records': 100_000},     # default: 10k; OpenAlex has cursor pagination
    'sec_edgar': {'max_records': 20_000},        # default: 5k; pharma filings 457 days
    # Patents (full 457-day window)
    'epo_ops': {'max_records': 20_000},          # default: 5k; EPO patent family search
    'uspto_patents': {'max_records': 50_000},    # default: 10k; PatentsView full history
    'uspto_ci': {'max_records': 50_000},         # default: 10k; CI patent subset
    # NIH Reporter: raise for full 457-day grant window
    'nih_reporter': {'max_records': 50_000},     # default: 10k; active pharma grants
    # FDA NDC: 100k+ products — paginator fetches all but explicit cap avoids early exit
    'fda_ndc': {'max_records': 150_000},
    # FDA drugs: ~30k applications
    'fda_drugs': {'max_records': 35_000},
    # FDA REMS: ~80 active REMS programs — small static set, full fetch
    'fda_rems': {'max_records': 200},
    # ---------------------------------------------------------------------------
    # CMS PUF multi-year backfill (service years 2021-2023).
    # Year-specific sub-UUIDs are discovered dynamically from data.cms.gov/data.json
    # (cached 24h via cms_downloader._get_catalog). No hardcoded UUIDs needed.
    # The most recent available service year is 2023 (12-18 month CMS lag).
    # ---------------------------------------------------------------------------
    # Physician & Other Practitioners — by Provider (NPI-level aggregate)
    'cms_physician_puf': {'years': [2021, 2022, 2023]},
    # Physician & Other Practitioners — by Provider and Service (HCPCS-level)
    'cms_physician_puf_services': {'years': [2021, 2022, 2023]},
    # Specialty subsets of physician_puf_services (same UUID, filtered by provider type)
    'cms_imaging_puf': {'years': [2021, 2022, 2023]},
    'cms_lab_services': {'years': [2021, 2022, 2023]},
    'cms_mental_health_puf': {'years': [2021, 2022, 2023]},
    'cms_telehealth_puf': {'years': [2021, 2022, 2023]},
    # Outpatient / Inpatient hospitals
    'cms_outpatient_puf': {'years': [2021, 2022, 2023]},
    'cms_inpatient_puf': {'years': [2021, 2022, 2023]},
    # Part D Prescribers (and opioid subset that uses same UUID)
    'cms_part_d_prescriber': {'years': [2021, 2022, 2023]},
    'cms_opioid_puf': {'years': [2021, 2022, 2023]},
    # Post-acute care
    'cms_dme_puf': {'years': [2021, 2022, 2023]},
    'cms_hospice_puf': {'years': [2021, 2022, 2023]},
    'cms_snf_puf': {'years': [2021, 2022, 2023]},
    'cms_home_health': {'years': [2021, 2022, 2023]},
    # Hospital cost reports
    'cms_cost_reports_puf': {'years': [2021, 2022, 2023]},
    'cms_cost_reports_puf_lines': {'years': [2021, 2022, 2023]},
    # Geographic / enrollment / chronic conditions
    'cms_geographic_variation': {'years': [2021, 2022, 2023]},
    'cms_chronic_conditions': {'years': [2021, 2022, 2023]},
    'cms_dual_eligible': {'years': [2021, 2022, 2023]},
    'cms_enrollment_puf': {'years': [2021, 2022, 2023]},
    'cms_claim_type_puf': {'years': [2021, 2022, 2023]},
    'cms_utilization_puf': {'years': [2021, 2022, 2023]},
    # Provider directory
    'cms_nppes': {'years': [2021, 2022, 2023]},
    'cms_referring_providers': {'years': [2021, 2022, 2023]},
    'cms_ordering_providers': {'years': [2021, 2022, 2023]},
    # Drug / payment
    'cms_part_d_spending': {'years': [2021, 2022, 2023]},
    'cms_part_b_spending': {'years': [2021, 2022, 2023]},
    'cms_open_payments': {'years': [2021, 2022, 2023]},
    'cms_medicaid_drug_spending': {'years': [2021, 2022, 2023]},
    'cms_medicare_advantage': {'years': [2021, 2022, 2023]},
    # Hospital info
    'cms_hospital_general_info': {'years': [2021, 2022, 2023]},
    # ---------------------------------------------------------------------------
    # New high-volume sources added in 019-cms-puf-platform-reconciliation
    # ---------------------------------------------------------------------------
    # ChEMBL molecules: ~2.4M compounds, paginated at 1000/req — full dataset needed.
    # No days_back for bulk reference data; None removes the cap entirely.
    'chembl_molecules': {'max_records': None},
    # PubChem: drug-relevant compound subset; ~2M records paginated via SDQ API.
    'pubchem': {'max_records': 2_000_000},
    # OpenFDA FAERS: year-partitioned same as openfda_labels; ~20M total adverse events.
    # full_backfill=True iterates receivedate:[YEAR0101 TO YEAR1231] per year.
    'openfda_faers': {'full_backfill': True},
    # NPI Registry: ~7M providers; fetcher paginates at 200/req with skip.
    'npi_registry': {'max_records': 7_000_000},
    # Purple Book (FDA BLAs): ~4k biological products — small dataset, no cap needed.
    'purple_book': {'max_records': 10_000},
    # Reactome: ~15k pathways; full reference dataset.
    'reactome': {'max_records': 25_000},
    # WHO GHO: health indicator data; moderate volume.
    'who_gho': {'max_records': 10_000},
    # NICE HTA: all guidance types (TA/HST/IPG/MTA); ~4k total records.
    'nice_hta': {'max_records': 5_000},
    # CMS Medicare: utilization/payment data; volume depends on dataset UUID.
    'cms_medicare': {'max_records': None},
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


def _fetch_one(source: str, data_dir: str, days_back: int | None,
               semaphore: Semaphore | None) -> tuple[str, str, int]:
    """Fetch a single source. Returns (source, status, records).

    Acquires semaphore if provided (rate-group throttle), releases on exit.
    Emits per-source Prometheus metrics: duration, record count, failure count.
    """
    if semaphore is not None:
        t_wait = time.monotonic()
        semaphore.acquire()
        record_job_duration(f'backfill_semaphore_wait_{source}', time.monotonic() - t_wait)
    t0 = time.monotonic()
    try:
        extra_kwargs = BACKFILL_SOURCE_KWARGS.get(source, {})
        result = run_ingestion(
            source=source,
            data_dir=data_dir,
            days_back=days_back,
            **extra_kwargs,
        )
        status = result.get('status', 'unknown')
        records = result.get('records_inserted', result.get('records_fetched', 0))
        elapsed = time.monotonic() - t0
        record_job_duration(f'backfill_fetch_{source}', elapsed)
        record_job_records(f'backfill_fetch_{source}', records or 0)
        if status not in ('success', 'partial'):
            increment_job_failure(f'backfill_fetch_{source}')
        return source, status, records
    except Exception:
        elapsed = time.monotonic() - t0
        record_job_duration(f'backfill_fetch_{source}', elapsed)
        increment_job_failure(f'backfill_fetch_{source}')
        raise
    finally:
        if semaphore is not None:
            semaphore.release()


def _build_semaphore_map() -> dict[str, Semaphore]:
    """Build a {source_name: Semaphore} map from API_RATE_GROUPS.

    Each named group gets its own Semaphore so groups with the same numeric limit
    do not share slots (e.g. CMS limit=2 and EBI limit=2 stay independent).
    Sources appearing in multiple groups get the most restrictive group's semaphore.
    Sources not in any group get None (no throttle beyond the thread pool itself).
    """
    # One Semaphore per named group — never share across groups.
    group_sems: dict[str, Semaphore] = {
        group: Semaphore(limit)
        for group, (limit, _) in API_RATE_GROUPS.items()
    }

    # For sources in multiple groups, pick the most restrictive (lowest limit) group.
    source_best: dict[str, tuple[int, str]] = {}  # source -> (best_limit, group_name)
    for group, (limit, sources) in API_RATE_GROUPS.items():
        for s in sources:
            if s not in source_best or limit < source_best[s][0]:
                source_best[s] = (limit, group)

    return {source: group_sems[group] for source, (_, group) in source_best.items()}


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
            record_job_duration('backfill_sqlmesh_plan', elapsed)
            mark_job_success('backfill_sqlmesh_plan')
            return True
        else:
            logger.error("SQLMesh plan failed (exit %d) after %.0fs", result.returncode, elapsed)
            record_job_duration('backfill_sqlmesh_plan', elapsed)
            increment_job_failure('backfill_sqlmesh_plan')
            return False
    except Exception as e:
        logger.error("SQLMesh plan raised exception: %s", e)
        increment_job_failure('backfill_sqlmesh_plan')
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


def run_fetch_backfill(data_dir: str, workers: int = 1, dry_run: bool = False) -> dict:
    """Fetch ALL sources.

    With workers=1 (default): sequential, identical to prior behaviour.
    With workers>1: light/medium sources run in a thread pool; heavy sources
    run sequentially afterward (memory safety).

    Returns dict of {source: status}.
    """
    days_back = compute_backfill_days()
    sources_to_run = [s for s in SOURCES if s not in SKIP_SOURCES]

    # Partition into (skip, heavy, light) — check skip first
    skip_list: list[tuple[str, str]] = []
    heavy_queue: list[str] = []
    light_queue: list[str] = []

    for source in sources_to_run:
        skip, reason = should_skip_source(source)
        if skip:
            skip_list.append((source, reason))
        elif source in HEAVY_SOURCES:
            heavy_queue.append(source)
        else:
            light_queue.append(source)

    total = len(light_queue) + len(heavy_queue)
    logger.info("=" * 60)
    logger.info("FETCH BACKFILL: %d sources (window=%d days since %s)",
                total, days_back, SQLMESH_START_DATE)
    logger.info("  Light/medium: %d  Heavy (sequential): %d  Skipped: %d  Workers: %d",
                len(light_queue), len(heavy_queue), len(skip_list), workers)
    logger.info("=" * 60)

    results: dict[str, str] = {}
    for source, reason in skip_list:
        logger.info("SKIP %s: %s", source, reason)
        results[source] = f"skipped: {reason}"

    if dry_run:
        for source in light_queue + heavy_queue:
            is_file = source in TIMELESS_SOURCES
            logger.info("DRY RUN %s: days_back=%s tier=%s",
                        source,
                        None if is_file else days_back,
                        'heavy' if source in HEAVY_SOURCES else 'light')
            results[source] = "dry-run"
        return results

    semaphore_map = _build_semaphore_map()
    success: list[str] = []
    failed: list[str] = []
    completed = 0

    # ----------------------------------------------------------------
    # Phase 1: light/medium sources — parallel
    # ----------------------------------------------------------------
    if light_queue:
        logger.info("Phase 1: parallel fetch (%d sources, %d workers)", len(light_queue), workers)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_source = {
                pool.submit(
                    _fetch_one,
                    source,
                    data_dir,
                    None if source in TIMELESS_SOURCES else days_back,
                    semaphore_map.get(source),
                ): source
                for source in light_queue
            }
            for future in as_completed(future_to_source):
                completed += 1
                try:
                    src, status, records = future.result()
                    logger.info("[%d/%d] %s: %s (%d records)",
                                completed, total, src, status.upper(), records)
                    results[src] = status
                    if status in ('success', 'partial'):
                        success.append(src)
                    else:
                        failed.append(src)
                except Exception as exc:
                    src = future_to_source[future]
                    logger.error("[%d/%d] %s: EXCEPTION — %s", completed, total, src, exc)
                    results[src] = f"exception: {exc}"
                    failed.append(src)

    # ----------------------------------------------------------------
    # Phase 2: heavy sources — sequential
    # ----------------------------------------------------------------
    if heavy_queue:
        logger.info("Phase 2: sequential heavy fetch (%d sources)", len(heavy_queue))
        for source in heavy_queue:
            completed += 1
            logger.info("[%d/%d] %s (heavy) — starting", completed, total, source)
            try:
                src, status, records = _fetch_one(
                    source,
                    data_dir,
                    None if source in TIMELESS_SOURCES else days_back,
                    semaphore_map.get(source),
                )
                logger.info("[%d/%d] %s: %s (%d records)",
                            completed, total, src, status.upper(), records)
                results[src] = status
                if status in ('success', 'partial'):
                    success.append(src)
                else:
                    failed.append(src)
            except Exception as exc:
                logger.error("[%d/%d] %s: EXCEPTION — %s", completed, total, source, exc)
                results[source] = f"exception: {exc}"
                failed.append(source)

    logger.info("")
    logger.info("FETCH BACKFILL COMPLETE:")
    logger.info("  Succeeded: %d  Failed: %d  Skipped: %d",
                len(success), len(failed), len(skip_list))
    if failed:
        logger.warning("  Failed sources: %s", ', '.join(failed))

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Initial full backfill: fetch all sources + SQLMesh historical plan',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full backfill, 4 parallel workers:
  python -m dk_data.ingestion.initial_backfill --workers 4

  # Fetch only (no sqlmesh):
  python -m dk_data.ingestion.initial_backfill --workers 4 --fetch-only

  # SQLMesh backfill only (data already in raw tables):
  python -m dk_data.ingestion.initial_backfill --sqlmesh-only

  # Dry run to see what would be fetched:
  python -m dk_data.ingestion.initial_backfill --workers 4 --dry-run
        """
    )
    parser.add_argument('--workers', type=int, default=1,
                        help='Parallel fetch workers for light/medium sources (default 1). '
                             'Recommended: 4 for the standard 4vCPU/8Gi pod.')
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

    if args.workers < 1:
        parser.error("--workers must be >= 1")

    Path(args.data_dir).mkdir(parents=True, exist_ok=True)

    # Initialize structured logging (JSON for Loki log correlation) and OTel tracing.
    # Must be called before any significant work so auto-instrumentation is active.
    # setup_telemetry() reads OTEL_EXPORTER_OTLP_ENDPOINT and OTEL_ENABLED from env;
    # it also auto-instruments requests, psycopg2, and httpx for distributed tracing.
    service_name = os.getenv("OTEL_SERVICE_NAME", "dk-data-initial-backfill")
    if _OBSERVABILITY_AVAILABLE:
        setup_logging(service_name)
        setup_telemetry(service_name)

    # Start Prometheus HTTP scrape endpoint (L2 — required for PodMonitor scraping)
    if _METRICS_AVAILABLE:
        try:
            start_http_server(METRICS_PORT)
            logger.info("Prometheus metrics available on :%d/metrics", METRICS_PORT)
        except Exception as e:
            logger.warning("Could not start Prometheus HTTP server: %s", e)

    overall_start = time.monotonic()
    logger.info("=" * 60)
    logger.info("INITIAL BACKFILL — dk-data platform")
    logger.info("SQLMesh start date: %s", SQLMESH_START_DATE)
    logger.info("Fetch window: %d days", compute_backfill_days())
    logger.info("Workers: %d", args.workers)
    logger.info("=" * 60)

    exit_code = 0

    if not args.sqlmesh_only:
        # Connection pool sized to workers * 3:
        # each worker can hold up to ~2 connections (fetch + loader), plus headroom.
        pool_size = max(10, args.workers * 3)
        init_connection_pool(minconn=2, maxconn=pool_size)
        try:
            fetch_results = run_fetch_backfill(
                args.data_dir,
                workers=args.workers,
                dry_run=args.dry_run,
            )
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
    record_job_duration('backfill_overall', elapsed)
    if exit_code == 0:
        mark_job_success('backfill_overall')
    else:
        increment_job_failure('backfill_overall')
    logger.info("=" * 60)
    logger.info("INITIAL BACKFILL COMPLETE in %.0f minutes", elapsed / 60)
    logger.info("=" * 60)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
