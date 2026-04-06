#!/usr/bin/env python3
"""Per-source backfill entrypoint — fetch → bronze transform → health check for ONE source.

This is a MANUAL, SEQUENTIAL job meant to be run one source at a time.
It does:
  1. Fetch  — calls run_ingestion() for the given source
  2. Bronze — runs `sqlmesh run --select-model <bronze_model>` for each of the
              source's bronze model(s)
  3. Health — queries bronze table(s) for row counts and grain-column nulls

Exit codes:
  0 — all stages passed
  1 — fetch failed
  2 — bronze transform failed
  3 — health check failed (row count 0 or null-grain issues)

Usage:
  python -m dk_data.ingestion.source_backfill --source chembl_molecules
  python -m dk_data.ingestion.source_backfill --source openfda_faers --days-back 730
  python -m dk_data.ingestion.source_backfill --source pubchem --fetch-only
  python -m dk_data.ingestion.source_backfill --source clinicaltrials --transform-only
  python -m dk_data.ingestion.source_backfill --source chembl_molecules --health-only
  python -m dk_data.ingestion.source_backfill --source fda_drugs --dry-run
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from .main import SOURCES, get_last_successful_refresh, run_ingestion
from .initial_backfill import compute_backfill_days

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s — %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

try:
    from dk_data.observability import setup_telemetry, setup_logging
    _OBSERVABILITY_AVAILABLE = True
except ImportError:
    _OBSERVABILITY_AVAILABLE = False
    def setup_telemetry(service_name, **kwargs): pass
    def setup_logging(service_name, **kwargs): pass

# ---------------------------------------------------------------------------
# Source → bronze model mapping
# ---------------------------------------------------------------------------

SOURCE_TO_BRONZE_MODELS: dict[str, list[str]] = {
    # mol_raw → mol_bronze
    'chembl_molecules':             ['mol_bronze.chembl_molecules'],
    'chembl_activities':            ['mol_bronze.chembl_activities'],
    'openfda_labels':               ['mol_bronze.openfda_labels'],
    'openfda_faers':                ['mol_bronze.faers_events'],
    'pubchem':                      ['mol_bronze.pubchem'],
    'drugbank':                     ['mol_bronze.drugbank'],
    'uniprot':                      ['mol_bronze.uniprot'],
    'rxnorm':                       ['mol_bronze.rxnorm'],
    'pharmgkb':                     ['mol_bronze.pharmgkb'],
    'bindingdb':                    ['mol_bronze.bindingdb'],
    'sider':                        ['mol_bronze.sider'],
    'tdc_admet':                    ['mol_bronze.tdc_admet'],
    'ttd':                          ['mol_bronze.ttd'],
    'cdc_vaccines':                 ['mol_bronze.cdc_vaccines'],
    'imgt':                         ['mol_bronze.imgt'],
    'kegg_drug':                    ['mol_bronze.kegg_drug'],
    'who_inn':                      ['mol_bronze.who_inn'],
    'who_gho':                      ['mol_bronze.who_gho'],
    'who_icd':                      ['mol_bronze.who_icd'],
    'purple_book':                  ['mol_bronze.purple_book'],
    'reactome':                     ['mol_bronze.reactome'],
    'orange_book':                  ['mol_bronze.orange_book'],
    'fda_drugs':                    ['mol_bronze.fda_drugs'],
    'fda_ndc':                      ['mol_bronze.fda_ndc'],
    'fda_rems':                     ['mol_bronze.fda_rems'],
    'nice_hta':                     ['mol_bronze.nice_hta'],
    'cms_coverage':                 ['mol_bronze.cms_coverage'],
    'ema':                          ['mol_bronze.ema', 'mol_bronze.ema_regulatory'],
    'europepmc':                    ['mol_bronze.europepmc'],
    'nih_reporter':                 ['mol_bronze.nih_reporter'],
    'clinicaltrials':               ['mol_bronze.clinicaltrials'],
    'dailymed':                     ['mol_bronze.dailymed'],
    'cms_medicare':                 ['mol_bronze.cms_medicare'],
    'npi_registry':                 ['mol_bronze.npi_registry'],
    'openalex_ci':                  ['mol_bronze.openalex'],
    'websearch':                    ['mol_bronze.websearch'],
    'pubmed':                       ['mol_bronze.pubmed'],
    'cochrane':                     ['mol_bronze.cochrane_reviews'],
    'sec_edgar':                    ['mol_bronze.sec_edgar'],
    'orcid':                        ['mol_bronze.orcid'],
    'journal_rss':                  ['mol_bronze.journal_rss'],
    'medical_news':                 ['mol_bronze.medical_news'],
    'hta_bodies':                   ['mol_bronze.hta_decisions'],
    'pdb':                          ['mol_bronze.pdb_structures'],
    'uspto_patents':                ['mol_bronze.uspto_patents'],
    'uspto_ci':                     ['mol_bronze.uspto_ci'],
    'epo_ops':                      ['mol_bronze.epo_patents'],
    'uspto_trademarks':             ['mol_bronze.uspto_trademarks'],
    'euipo_designs':                ['mol_bronze.euipo_designs'],
    'cms_open_payments':            ['mol_bronze.cms_open_payments'],
    # hcs_raw → hcs_bronze
    'cms_inpatient':                ['hcs_bronze.cms_inpatient'],
    'cms_hospital_info':            ['hcs_bronze.cms_hospital_info'],
    'cms_cost_reports':             ['hcs_bronze.cms_cost_reports'],
    'acc_tvc':                      ['hcs_bronze.acc_tvc'],
    'hrsa':                         ['hcs_bronze.hrsa'],
    'cms_care_compare':             ['hcs_bronze.cms_care_compare'],
    'cms_chow':                     ['hcs_bronze.cms_chow'],
    'cms_dmepos':                   ['hcs_bronze.cms_dmepos'],
    'cms_formulary':                ['hcs_bronze.cms_formulary'],
    'cms_hcris':                    ['hcs_bronze.cms_hcris'],
    'cms_hospital_affiliation':     ['hcs_bronze.cms_hospital_affiliation'],
    'cms_hospital_quality':         ['hcs_bronze.cms_hospital_quality'],
    'cms_magnet':                   ['hcs_bronze.cms_magnet'],
    'cms_ndc':                      ['hcs_bronze.cms_ndc'],
    'cms_nucc':                     ['hcs_bronze.cms_nucc'],
    'cms_pecos':                    ['hcs_bronze.cms_pecos'],
    'cms_pos':                      ['hcs_bronze.cms_pos'],
    'cms_post_acute':               ['hcs_bronze.cms_post_acute'],
    'cms_rbcs':                     ['hcs_bronze.cms_rbcs'],
    'cms_stabilis':                 ['hcs_bronze.cms_stabilis'],
    'cms_usp':                      ['hcs_bronze.cms_usp'],
    'cms_nppes':                    ['hcs_bronze.cms_nppes'],
    'cms_physician_puf':            ['hcs_bronze.cms_physician_puf'],
    'cms_physician_puf_services':   ['hcs_bronze.cms_physician_puf_services'],
    'cms_part_d_prescriber':        ['hcs_bronze.cms_part_d_prescriber'],
    'cms_part_d_spending':          ['hcs_bronze.cms_part_d_spending'],
    'cms_part_b_spending':          ['hcs_bronze.cms_part_b_spending'],
    'cms_geographic_variation':     ['hcs_bronze.cms_geographic_variation'],
    'cms_inpatient_puf':            ['hcs_bronze.cms_inpatient_puf'],
    'cms_hospital_general_info':    ['hcs_bronze.cms_hospital_general_info'],
    'cms_medicare_advantage':       ['hcs_bronze.cms_medicare_advantage'],
    'cms_medicaid_drug_spending':   ['hcs_bronze.cms_medicaid_drug_spending'],
    'cms_dme_puf':                  ['hcs_bronze.cms_dme_puf'],
    'cms_home_health':              ['hcs_bronze.cms_home_health'],
    'cms_hospice_puf':              ['hcs_bronze.cms_hospice_puf'],
    'cms_snf_puf':                  ['hcs_bronze.cms_snf_puf'],
    'cms_outpatient_puf':           ['hcs_bronze.cms_outpatient_puf'],
    'cms_referring_providers':      ['hcs_bronze.cms_referring_providers'],
    'cms_ordering_providers':       ['hcs_bronze.cms_ordering_providers'],
    'cms_lab_services':             ['hcs_bronze.cms_lab_services'],
    'cms_imaging_puf':              ['hcs_bronze.cms_imaging_puf'],
    'cms_mental_health_puf':        ['hcs_bronze.cms_mental_health_puf'],
    'cms_opioid_puf':               ['hcs_bronze.cms_opioid_puf'],
    'cms_telehealth_puf':           ['hcs_bronze.cms_telehealth_puf'],
    'cms_chronic_conditions':       ['hcs_bronze.cms_chronic_conditions'],
    'cms_dual_eligible':            ['hcs_bronze.cms_dual_eligible'],
    'cms_enrollment_puf':           ['hcs_bronze.cms_enrollment_puf'],
    'cms_claim_type_puf':           ['hcs_bronze.cms_claim_type_puf'],
    'cms_utilization_puf':          ['hcs_bronze.cms_utilization_puf'],
    'cms_cost_reports_puf':         ['hcs_bronze.cms_cost_reports_puf'],
    'cms_cost_reports_puf_lines':   ['hcs_bronze.cms_cost_reports_puf_lines'],
    'cms_ddinter':                  ['hcs_bronze.cms_ddinter'],
}

# Grain column per bronze model — used for null-count health check.
# If a model is not listed here, the null check is skipped (pass open).
MODEL_GRAIN_COLUMN: dict[str, str] = {
    'mol_bronze.chembl_molecules':          'molecule_chembl_id',
    'mol_bronze.chembl_activities':         'activity_id',
    'mol_bronze.openfda_labels':            'set_id',
    'mol_bronze.faers_events':              'safetyreportid',
    'mol_bronze.pubchem':                   'cid',
    'mol_bronze.drugbank':                  'drugbank_id',
    'mol_bronze.uniprot':                   'entry_name',
    'mol_bronze.rxnorm':                    'rxcui',
    'mol_bronze.pharmgkb':                  'pharmgkb_id',
    'mol_bronze.bindingdb':                 'monomerid',
    'mol_bronze.sider':                     'stitch_id',
    'mol_bronze.tdc_admet':                 'id',
    'mol_bronze.ttd':                       'ttd_drug_id',
    'mol_bronze.cdc_vaccines':              'id',
    'mol_bronze.imgt':                      'id',
    'mol_bronze.kegg_drug':                 'drug_id',
    'mol_bronze.who_inn':                   'id',
    'mol_bronze.who_gho':                   'id',
    'mol_bronze.who_icd':                   'code',
    'mol_bronze.purple_book':               'bla_number',
    'mol_bronze.reactome':                  'pathway_id',
    'mol_bronze.orange_book':               'appl_no',
    'mol_bronze.fda_drugs':                 'application_number',
    'mol_bronze.fda_ndc':                   'product_ndc',
    'mol_bronze.fda_rems':                  'id',
    'mol_bronze.nice_hta':                  'id',
    'mol_bronze.cms_coverage':              'id',
    'mol_bronze.ema':                       'id',
    'mol_bronze.ema_regulatory':            'id',
    'mol_bronze.europepmc':                 'id',
    'mol_bronze.nih_reporter':              'project_num',
    'mol_bronze.clinicaltrials':            'nct_id',
    'mol_bronze.dailymed':                  'set_id',
    'mol_bronze.cms_medicare':              'id',
    'mol_bronze.npi_registry':              'npi',
    'mol_bronze.openalex':                  'id',
    'mol_bronze.websearch':                 'id',
    'mol_bronze.pubmed':                    'pmid',
    'mol_bronze.cochrane_reviews':          'id',
    'mol_bronze.sec_edgar':                 'accession_number',
    'mol_bronze.orcid':                     'orcid_id',
    'mol_bronze.journal_rss':               'id',
    'mol_bronze.medical_news':              'id',
    'mol_bronze.hta_decisions':             'id',
    'mol_bronze.pdb_structures':            'pdb_id',
    'mol_bronze.uspto_patents':             'patent_id',
    'mol_bronze.uspto_ci':                  'patent_number',
    'mol_bronze.epo_patents':               'patent_number',
    'mol_bronze.uspto_trademarks':          'serial_number',
    'mol_bronze.euipo_designs':             'id',
    'mol_bronze.cms_open_payments':         'record_id',
    'hcs_bronze.cms_inpatient':             'id',
    'hcs_bronze.cms_hospital_info':         'provider_id',
    'hcs_bronze.cms_cost_reports':          'id',
    'hcs_bronze.acc_tvc':                   'id',
    'hcs_bronze.hrsa':                      'id',
    'hcs_bronze.cms_care_compare':          'id',
    'hcs_bronze.cms_chow':                  'id',
    'hcs_bronze.cms_dmepos':                'npi',
    'hcs_bronze.cms_formulary':             'id',
    'hcs_bronze.cms_hcris':                 'id',
    'hcs_bronze.cms_hospital_affiliation':  'id',
    'hcs_bronze.cms_hospital_quality':      'provider_id',
    'hcs_bronze.cms_magnet':                'id',
    'hcs_bronze.cms_ndc':                   'ndc_code',
    'hcs_bronze.cms_nucc':                  'code',
    'hcs_bronze.cms_pecos':                 'npi',
    'hcs_bronze.cms_pos':                   'id',
    'hcs_bronze.cms_post_acute':            'id',
    'hcs_bronze.cms_rbcs':                  'id',
    'hcs_bronze.cms_stabilis':              'id',
    'hcs_bronze.cms_usp':                   'id',
    'hcs_bronze.cms_nppes':                 'npi',
    'hcs_bronze.cms_physician_puf':         'npi',
    'hcs_bronze.cms_physician_puf_services':'npi',
    'hcs_bronze.cms_part_d_prescriber':     'npi',
    'hcs_bronze.cms_part_d_spending':       'id',
    'hcs_bronze.cms_part_b_spending':       'id',
    'hcs_bronze.cms_geographic_variation':  'id',
    'hcs_bronze.cms_inpatient_puf':         'id',
    'hcs_bronze.cms_hospital_general_info': 'provider_id',
    'hcs_bronze.cms_medicare_advantage':    'id',
    'hcs_bronze.cms_medicaid_drug_spending':'id',
    'hcs_bronze.cms_dme_puf':              'npi',
    'hcs_bronze.cms_home_health':           'id',
    'hcs_bronze.cms_hospice_puf':          'id',
    'hcs_bronze.cms_snf_puf':             'id',
    'hcs_bronze.cms_outpatient_puf':       'id',
    'hcs_bronze.cms_referring_providers':  'npi',
    'hcs_bronze.cms_ordering_providers':   'npi',
    'hcs_bronze.cms_lab_services':         'id',
    'hcs_bronze.cms_imaging_puf':          'id',
    'hcs_bronze.cms_mental_health_puf':    'id',
    'hcs_bronze.cms_opioid_puf':           'npi',
    'hcs_bronze.cms_telehealth_puf':       'id',
    'hcs_bronze.cms_chronic_conditions':   'id',
    'hcs_bronze.cms_dual_eligible':        'id',
    'hcs_bronze.cms_enrollment_puf':       'id',
    'hcs_bronze.cms_claim_type_puf':       'id',
    'hcs_bronze.cms_utilization_puf':      'id',
    'hcs_bronze.cms_cost_reports_puf':     'id',
    'hcs_bronze.cms_cost_reports_puf_lines':'id',
    'hcs_bronze.cms_ddinter':              'id',
}

# Default SQLMesh project directory (relative path used when invoked from repo root).
SQLMESH_DIR = 'src/dk_data/sqlmesh'


# ---------------------------------------------------------------------------
# Stage 1: Fetch
# ---------------------------------------------------------------------------

def run_fetch(source: str, days_back: int | None, data_dir: str, dry_run: bool) -> bool:
    """Fetch raw data for a single source.

    Returns True on success, False on failure.
    """
    logger.info("=" * 60)
    logger.info("STAGE 1 — FETCH: %s  (days_back=%s)", source, days_back)
    logger.info("=" * 60)

    if dry_run:
        logger.info("DRY RUN: would call run_ingestion(source=%r, days_back=%s, data_dir=%r)",
                    source, days_back, data_dir)
        return True

    Path(data_dir).mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    try:
        result = run_ingestion(
            source=source,
            days_back=days_back,
            data_dir=data_dir,
        )
    except Exception as exc:
        logger.error("Fetch raised exception for %s: %s", source, exc)
        return False

    elapsed = time.monotonic() - t0
    status = result.get('status', 'unknown') if isinstance(result, dict) else 'unknown'
    records = (result.get('records_inserted', result.get('records_fetched', 0))
               if isinstance(result, dict) else 0)
    logger.info("Fetch finished in %.0fs: status=%s records=%s", elapsed, status, records)

    if status in ('success', 'partial'):
        return True
    else:
        logger.error("Fetch FAILED for %s: %s", source, result)
        return False


# ---------------------------------------------------------------------------
# Stage 2: Bronze transform
# ---------------------------------------------------------------------------

def run_bronze_transform(bronze_models: list[str], sqlmesh_dir: str, dry_run: bool) -> bool:
    """Run `sqlmesh run --select-model <model>` for each bronze model.

    Returns True if all models succeed, False if any fail.
    """
    logger.info("=" * 60)
    logger.info("STAGE 2 — BRONZE TRANSFORM: %s", ', '.join(bronze_models))
    logger.info("=" * 60)

    if not bronze_models:
        logger.warning("No bronze models configured for this source — skipping transform")
        return True

    sqlmesh_path = str(Path(sqlmesh_dir).resolve())
    all_ok = True

    for model in bronze_models:
        if dry_run:
            logger.info("DRY RUN: would run sqlmesh run --select-model %s", model)
            continue

        logger.info("Running: sqlmesh run --select-model %s", model)
        t0 = time.monotonic()
        try:
            result = subprocess.run(
                ['python', '-m', 'sqlmesh', '--path', sqlmesh_path,
                 'run', '--select-model', model],
                capture_output=False,   # stream directly to pod logs
                timeout=3600,           # 1 hour per model should be generous
                env={
                    **os.environ,
                    'HOME': '/tmp',     # avoid read-only home dir in container
                },
            )
            elapsed = time.monotonic() - t0
            if result.returncode == 0:
                logger.info("Transform %s succeeded in %.0fs", model, elapsed)
            else:
                logger.error("Transform %s FAILED (exit %d) in %.0fs",
                             model, result.returncode, elapsed)
                all_ok = False
        except subprocess.TimeoutExpired:
            logger.error("Transform %s timed out after 3600s", model)
            all_ok = False
        except Exception as exc:
            logger.error("Transform %s raised exception: %s", model, exc)
            all_ok = False

    return all_ok


# ---------------------------------------------------------------------------
# Stage 3: Health check
# ---------------------------------------------------------------------------

def _db_connect():
    """Open a psycopg2 connection using standard POSTGRES_* env vars."""
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        dbname=os.getenv("POSTGRES_DB", "dk_data"),
    )


def _check_model_health(schema: str, table: str, grain_col: str | None) -> dict:
    """Run health checks on a single bronze table.

    Returns:
        {
            'model': 'schema.table',
            'table_exists': bool,
            'row_count': int | None,
            'null_grain_count': int | None,   # None if grain_col not provided / table missing
            'pass': bool,
            'warnings': list[str],
        }
    """
    model_key = f"{schema}.{table}"
    result = {
        'model': model_key,
        'table_exists': False,
        'row_count': None,
        'null_grain_count': None,
        'pass': True,
        'warnings': [],
    }

    try:
        conn = _db_connect()
        cur = conn.cursor()

        # 1. Check table exists
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE schemaname = %s AND tablename = %s)",
            (schema, table),
        )
        table_exists = bool(cur.fetchone()[0])
        result['table_exists'] = table_exists

        if not table_exists:
            result['warnings'].append(f"Table {model_key} does not exist yet")
            # Not a hard fail — table may not have been created by SQLMesh yet
            conn.close()
            return result

        # 2. Row count
        cur.execute(f"SELECT COUNT(*) FROM {schema}.{table}")
        row_count = int(cur.fetchone()[0])
        result['row_count'] = row_count
        if row_count == 0:
            result['warnings'].append(f"Table {model_key} has 0 rows")
            result['pass'] = False

        # 3. Null grain count (only if grain column is configured)
        if grain_col and row_count > 0:
            try:
                cur.execute(
                    f"SELECT COUNT(*) FROM {schema}.{table} WHERE {grain_col} IS NULL"
                )
                null_count = int(cur.fetchone()[0])
                result['null_grain_count'] = null_count
                if null_count > 0:
                    pct = null_count / row_count * 100
                    result['warnings'].append(
                        f"{null_count} rows ({pct:.1f}%) have NULL {grain_col}"
                    )
                    result['pass'] = False
            except Exception as exc:
                result['warnings'].append(
                    f"Grain column check failed for {grain_col}: {exc} (skipped)"
                )

        # 4. Check sqlmesh._audits for recent failures (fail open if table missing)
        try:
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE schemaname = 'sqlmesh' "
                "AND tablename = '_audits')"
            )
            audits_exist = bool(cur.fetchone()[0])
            if audits_exist:
                cur.execute(
                    "SELECT COUNT(*) FROM sqlmesh._audits "
                    "WHERE model_name = %s AND count > 0",
                    (model_key,),
                )
                audit_failures = int(cur.fetchone()[0])
                if audit_failures > 0:
                    result['warnings'].append(
                        f"{audit_failures} SQLMesh audit failure(s) recorded for {model_key}"
                    )
                    result['pass'] = False
        except Exception:
            pass  # fail open — audits table structure may vary

        conn.close()

    except Exception as exc:
        result['warnings'].append(f"DB connection error: {exc}")
        # Fail open on connectivity issues — don't mask fetch/transform results
        logger.warning("Health check DB error for %s: %s — skipping", model_key, exc)

    return result


def run_health_check(bronze_models: list[str], dry_run: bool) -> bool:
    """Run health checks for all bronze models of a source.

    Prints a summary table and returns True if all pass, False if any fail.
    """
    logger.info("=" * 60)
    logger.info("STAGE 3 — HEALTH CHECK: %s", ', '.join(bronze_models))
    logger.info("=" * 60)

    if not bronze_models:
        logger.warning("No bronze models configured — skipping health check")
        return True

    if dry_run:
        for model in bronze_models:
            logger.info("DRY RUN: would health-check %s", model)
        return True

    all_pass = True
    check_results = []

    for model_fqn in bronze_models:
        parts = model_fqn.split('.')
        if len(parts) != 2:
            logger.warning("Unexpected model format (expected schema.table): %s — skipping", model_fqn)
            continue
        schema, table = parts
        grain_col = MODEL_GRAIN_COLUMN.get(model_fqn)
        check = _check_model_health(schema, table, grain_col)
        check_results.append(check)
        if not check['pass']:
            all_pass = False

    # Print summary table
    logger.info("")
    logger.info("%-50s %10s %12s %10s", "MODEL", "ROWS", "NULL_GRAIN", "STATUS")
    logger.info("-" * 90)
    for c in check_results:
        row_count_str = str(c['row_count']) if c['row_count'] is not None else 'N/A'
        null_str = str(c['null_grain_count']) if c['null_grain_count'] is not None else 'N/A'
        status = "PASS" if c['pass'] else "FAIL"
        logger.info("%-50s %10s %12s %10s", c['model'], row_count_str, null_str, status)
        for warn in c['warnings']:
            logger.warning("  WARNING: %s", warn)
    logger.info("-" * 90)
    logger.info("Overall health: %s", "PASS" if all_pass else "FAIL")
    logger.info("")

    return all_pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Per-source backfill: fetch → bronze transform → health check',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline for one source:
  python -m dk_data.ingestion.source_backfill --source chembl_molecules

  # Fetch only (populate raw table):
  python -m dk_data.ingestion.source_backfill --source pubchem --fetch-only

  # Transform only (raw already populated, run bronze SQLMesh model):
  python -m dk_data.ingestion.source_backfill --source pubchem --transform-only

  # Health check only (verify bronze table state):
  python -m dk_data.ingestion.source_backfill --source pubchem --health-only

  # Dry run (show what would happen):
  python -m dk_data.ingestion.source_backfill --source clinicaltrials --dry-run

  # Custom days-back window:
  python -m dk_data.ingestion.source_backfill --source nih_reporter --days-back 365
        """,
    )
    parser.add_argument('--source', required=True,
                        help='Source name to backfill (e.g. chembl_molecules, pubchem)')
    parser.add_argument('--days-back', type=int, default=None,
                        help='Number of days to fetch (default: compute from SQLMESH_START_DATE)')
    parser.add_argument('--data-dir', default='/tmp/data/raw',
                        help='Directory for fetcher temp file storage (default: /tmp/data/raw)')
    parser.add_argument('--sqlmesh-dir', default=SQLMESH_DIR,
                        help=f'Path to SQLMesh project directory (default: {SQLMESH_DIR})')
    parser.add_argument('--fetch-only', action='store_true',
                        help='Only run the fetch stage')
    parser.add_argument('--transform-only', action='store_true',
                        help='Only run the bronze transform stage')
    parser.add_argument('--health-only', action='store_true',
                        help='Only run the health check stage')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without executing anything')

    args = parser.parse_args()

    # Validate mutually exclusive stage flags
    stage_flags = [args.fetch_only, args.transform_only, args.health_only]
    if sum(stage_flags) > 1:
        parser.error("--fetch-only, --transform-only, and --health-only are mutually exclusive")

    source = args.source

    # Validate source is known
    if source not in SOURCES and source not in SOURCE_TO_BRONZE_MODELS:
        logger.warning(
            "Source %r is not in SOURCES registry — proceeding with bronze model mapping only",
            source,
        )
    if source not in SOURCE_TO_BRONZE_MODELS:
        logger.error(
            "Source %r has no bronze model mapping in SOURCE_TO_BRONZE_MODELS. "
            "Add it to the mapping dict in source_backfill.py and retry.",
            source,
        )
        sys.exit(1)

    bronze_models = SOURCE_TO_BRONZE_MODELS[source]
    days_back = args.days_back if args.days_back is not None else compute_backfill_days()

    # Set up logging/telemetry
    service_name = os.getenv("OTEL_SERVICE_NAME", f"dk-data-source-backfill-{source}")
    if _OBSERVABILITY_AVAILABLE:
        setup_logging(service_name)
        setup_telemetry(service_name)

    logger.info("=" * 60)
    logger.info("SOURCE BACKFILL — %s", source)
    logger.info("Bronze models: %s", ', '.join(bronze_models))
    logger.info("Days back: %d", days_back)
    logger.info("Data dir: %s", args.data_dir)
    logger.info("SQLMesh dir: %s", args.sqlmesh_dir)
    if args.dry_run:
        logger.info("DRY RUN — no actual work will be performed")
    logger.info("=" * 60)

    # Determine which stages to run
    run_all = not any(stage_flags)
    do_fetch = run_all or args.fetch_only
    do_transform = run_all or args.transform_only
    do_health = run_all or args.health_only

    overall_start = time.monotonic()

    # Stage 1: Fetch
    if do_fetch:
        ok = run_fetch(source, days_back, args.data_dir, args.dry_run)
        if not ok:
            logger.error("Fetch stage FAILED — aborting")
            sys.exit(1)

    # Stage 2: Bronze transform
    if do_transform:
        ok = run_bronze_transform(bronze_models, args.sqlmesh_dir, args.dry_run)
        if not ok:
            logger.error("Bronze transform stage FAILED — aborting")
            sys.exit(2)

    # Stage 3: Health check
    if do_health:
        ok = run_health_check(bronze_models, args.dry_run)
        if not ok:
            logger.error("Health check FAILED — one or more bronze tables have issues")
            sys.exit(3)

    elapsed = time.monotonic() - overall_start
    logger.info("=" * 60)
    logger.info("SOURCE BACKFILL COMPLETE: %s (%.0fs)", source, elapsed)
    logger.info("=" * 60)
    sys.exit(0)


if __name__ == '__main__':
    main()
