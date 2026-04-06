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
# Prioritized backfill order — fastest to slowest
#
# Nick's principle: "scale out, not up — simple modular functions, one at a time"
# Never run more than 1 source concurrently during initial provisioning.
# Each tier is a rough estimate; actual time depends on API rate limits.
#
# Tier 1 — fast reference data (<5 min each)
# Tier 2 — medium API sources (5–30 min each)
# Tier 3 — larger API/file sources (30 min–4 h each)
# Tier 4 — heavy sequential (each needs its own day: 4–12 h)
# Tier 5 — extreme last (pubchem: 85 h at rate limit)
# ---------------------------------------------------------------------------
BACKFILL_ORDER: list[str] = [
    # ── Tier 1: fast reference data ──────────────────────────────────────
    'who_inn',              # WHO INN drug names   (~200 rows)
    'who_gho',              # WHO GHO indicators   (~1k rows)
    'kegg_drug',            # KEGG drug DB         (~11k rows)
    'rxnorm',               # NLM RxNorm concepts  (~100k rows, fast API)
    'imgt',                 # IMGT antibody seqs   (~1k rows)
    'cdc_vaccines',         # CDC CVX/MVX codes    (~300 rows)
    'cms_nucc',             # NUCC taxonomy        (~900 rows)
    'cms_rbcs',             # CMS RBCS codes       (~1k rows)
    'cms_usp',              # CMS USP drug classes (~1k rows)
    'cms_stabilis',         # CMS Stabilis drug info (~5k rows)
    'cms_pos',              # CMS Place of Service (~100 rows)
    'cms_chow',             # CMS CHOW ownership   (~10k rows)
    'fda_rems',             # FDA REMS programs    (~70 programs)
    'purple_book',          # FDA Biologics        (~3k rows)
    'nice_hta',             # NICE HTA decisions   (~5k rows)
    # ── Tier 2: medium API sources ───────────────────────────────────────
    'pharmgkb',             # PharmGKB annotations (~8k rows)
    'tdc_admet',            # TDC ADMET data       (~12k rows)
    'sider',                # SIDER side effects   (~140k rows)
    'ttd',                  # TTD drug targets     (~37k rows)
    'orange_book',          # FDA Orange Book      (~100k rows)
    'fda_drugs',            # FDA drug approvals   (~50k rows)
    'reactome',             # Reactome pathways    (~15k rows)
    'bindingdb',            # BindingDB affinities (~2.5M rows, batched)
    'who_icd',              # WHO ICD-11 codes     (~80k rows)
    'hrsa',                 # HRSA shortage areas  (~30k rows)
    'ema',                  # EMA drug data        (~2k rows)
    'dailymed',             # DailyMed labels      (~140k rows)
    'pdb',                  # PDB structures       (~220k rows, weekly batch)
    'cochrane',             # Cochrane reviews     (~10k rows)
    'hta_bodies',           # HTA body decisions   (~5k rows)
    'sec_edgar',            # SEC EDGAR filings    (~daily incremental)
    'journal_rss',          # Journal RSS feeds    (~daily incremental)
    'medical_news',         # Medical news         (~daily incremental)
    'websearch',            # Web search results   (~small)
    # ── Tier 3: larger API / file sources ────────────────────────────────
    'europepmc',            # Europe PMC articles  (~500k rows)
    'nih_reporter',         # NIH grants           (~200k rows)
    'clinicaltrials',       # ClinicalTrials.gov   (~500k rows)
    'openfda_labels',       # FDA drug labels      (~180k rows)
    'fda_ndc',              # FDA NDC directory    (~800k rows)
    'cms_coverage',         # CMS NCD coverage     (~100k rows)
    'cms_medicare',         # CMS Medicare spend   (~large file)
    'npi_registry',         # CMS NPI registry     (~8M rows, batched)
    'openalex_ci',          # OpenAlex CI search   (~daily incremental)
    'pubmed',               # PubMed articles      (~daily incremental)
    'drugbank',             # DrugBank             (~14k drugs)
    'epo_ops',              # EPO patents          (~weekly batch)
    'uspto_trademarks',     # USPTO trademarks     (~weekly batch)
    'euipo_designs',        # EUIPO designs        (~weekly batch)
    'uspto_ci',             # USPTO CI patents     (~weekly batch)
    'uspto_patents',        # USPTO patents        (~weekly batch)
    # CMS facility / provider sources
    'cms_care_compare',     'cms_hospital_affiliation', 'cms_hospital_quality',
    'cms_hospital_general_info', 'cms_home_health',    'cms_formulary',
    'cms_hospital_info',    'cms_hcris',               'cms_dmepos',
    'cms_magnet',           'cms_ndc',                 'cms_pecos',
    'cms_post_acute',       'cms_nppes',               'cms_geographic_variation',
    # CMS PUF sources (annual releases)
    'cms_inpatient_puf',    'cms_physician_puf',       'cms_physician_puf_services',
    'cms_part_d_prescriber','cms_part_d_spending',     'cms_part_b_spending',
    'cms_outpatient_puf',   'cms_opioid_puf',          'cms_ordering_providers',
    'cms_referring_providers','cms_imaging_puf',       'cms_lab_services',
    'cms_mental_health_puf','cms_telehealth_puf',      'cms_snf_puf',
    'cms_hospice_puf',      'cms_dme_puf',             'cms_utilization_puf',
    'cms_claim_type_puf',   'cms_enrollment_puf',      'cms_cost_reports_puf',
    'cms_cost_reports_puf_lines', 'cms_inpatient',     'cms_cost_reports',
    'cms_medicare_advantage','cms_medicaid_drug_spending','cms_chronic_conditions',
    'cms_dual_eligible',    'cms_open_payments',
    # Other HCS sources
    'acc_tvc',              'hrsa',
    # ── Tier 4: heavy sequential (4–12 h each) ───────────────────────────
    'openfda_faers',        # OpenFDA FAERS adverse events (~20M rows)
    'chembl_activities',    # ChEMBL activities            (~20M rows)
    'uniprot',              # UniProt protein DB           (~250k entries, large XML)
    'chembl_molecules',     # ChEMBL molecules             (~2.5M rows)
    # ── Tier 5: extreme — run last, alone, over a weekend ────────────────
    'pubchem',              # PubChem compounds — 123M rows, ~85h at rate limit
]


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

def run_all_sequential(
    args,
    days_back: int,
    stop_on_failure: bool,
) -> int:
    """Iterate through BACKFILL_ORDER, running fetch→transform→health for each source.

    Skips sources that already have a recent last_successful_refresh.
    Returns exit code: 0 = all passed, 1 = one or more failed.
    """
    from .initial_backfill import should_skip_source

    total = len(BACKFILL_ORDER)
    failed: list[str] = []
    skipped: list[str] = []

    logger.info("=" * 60)
    logger.info("SEQUENTIAL FULL BACKFILL — %d sources in BACKFILL_ORDER", total)
    logger.info("One source at a time. Stops on health failure unless --no-stop-on-failure.")
    logger.info("=" * 60)

    for idx, source in enumerate(BACKFILL_ORDER, 1):
        if source not in SOURCE_TO_BRONZE_MODELS:
            logger.warning("[%d/%d] %s — no bronze model mapping, skipping", idx, total, source)
            skipped.append(source)
            continue

        should_skip, reason = should_skip_source(source)
        if should_skip:
            logger.info("[%d/%d] %s — SKIP (%s)", idx, total, source, reason)
            skipped.append(source)
            continue

        logger.info("")
        logger.info("[%d/%d] ━━━ %s ━━━", idx, total, source.upper())
        bronze_models = SOURCE_TO_BRONZE_MODELS[source]

        ok = True

        if not (args.transform_only or args.health_only):
            ok = run_fetch(source, days_back, args.data_dir, args.dry_run)
            if not ok:
                logger.error("[%d/%d] %s — fetch FAILED", idx, total, source)
                failed.append(source)
                if stop_on_failure:
                    logger.error("Stopping (--stop-on-failure). Fix %s and re-run.", source)
                    break
                continue

        if ok and not (args.fetch_only or args.health_only):
            ok = run_bronze_transform(bronze_models, args.sqlmesh_dir, args.dry_run)
            if not ok:
                logger.error("[%d/%d] %s — bronze transform FAILED", idx, total, source)
                failed.append(source)
                if stop_on_failure:
                    logger.error("Stopping (--stop-on-failure). Fix %s and re-run.", source)
                    break
                continue

        if ok and not (args.fetch_only or args.transform_only):
            ok = run_health_check(bronze_models, args.dry_run)
            if not ok:
                logger.error("[%d/%d] %s — health check FAILED", idx, total, source)
                failed.append(source)
                if stop_on_failure:
                    logger.error("Stopping (--stop-on-failure). Investigate %s before continuing.", source)
                    break
                continue

        logger.info("[%d/%d] %s — DONE", idx, total, source)

    logger.info("")
    logger.info("=" * 60)
    logger.info("SEQUENTIAL BACKFILL COMPLETE")
    logger.info("  Sources in order : %d", total)
    logger.info("  Skipped          : %d", len(skipped))
    logger.info("  Failed           : %d  %s", len(failed), failed if failed else "")
    logger.info("=" * 60)

    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(
        description='Per-source backfill: fetch → bronze transform → health check',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single source — full pipeline:
  python -m dk_data.ingestion.source_backfill --source chembl_molecules

  # Full sequential initial backfill (Nick's way — one source at a time):
  python -m dk_data.ingestion.source_backfill --run-all
  python -m dk_data.ingestion.source_backfill --run-all --stop-on-failure

  # Fetch only (populate raw, skip transform):
  python -m dk_data.ingestion.source_backfill --source pubchem --fetch-only
  python -m dk_data.ingestion.source_backfill --run-all --fetch-only

  # Transform only (raw already populated):
  python -m dk_data.ingestion.source_backfill --source pubchem --transform-only

  # Health check only:
  python -m dk_data.ingestion.source_backfill --source pubchem --health-only

  # Dry run (show what would happen without running):
  python -m dk_data.ingestion.source_backfill --run-all --dry-run

  # Custom days-back window:
  python -m dk_data.ingestion.source_backfill --source nih_reporter --days-back 365
        """,
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument('--source',
                        help='Single source name to backfill (e.g. chembl_molecules, pubchem)')
    source_group.add_argument('--run-all', action='store_true',
                        help='Run all sources in BACKFILL_ORDER sequentially (initial provisioning)')
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
    parser.add_argument('--stop-on-failure', action='store_true',
                        help='(--run-all only) Stop the sequence on the first health-check failure')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without executing anything')

    args = parser.parse_args()

    # Validate mutually exclusive stage flags
    stage_flags = [args.fetch_only, args.transform_only, args.health_only]
    if sum(stage_flags) > 1:
        parser.error("--fetch-only, --transform-only, and --health-only are mutually exclusive")

    days_back = args.days_back if args.days_back is not None else compute_backfill_days()

    service_name = os.getenv("OTEL_SERVICE_NAME", "dk-data-source-backfill")
    if _OBSERVABILITY_AVAILABLE:
        setup_logging(service_name)
        setup_telemetry(service_name)

    # ── --run-all: sequential full backfill ──────────────────────────────
    if args.run_all:
        exit_code = run_all_sequential(
            args,
            days_back=days_back,
            stop_on_failure=args.stop_on_failure,
        )
        sys.exit(exit_code)

    # ── single source ────────────────────────────────────────────────────
    source = args.source

    if source not in SOURCES and source not in SOURCE_TO_BRONZE_MODELS:
        logger.warning(
            "Source %r is not in SOURCES registry — proceeding with bronze model mapping only",
            source,
        )
    if source not in SOURCE_TO_BRONZE_MODELS:
        logger.error(
            "Source %r has no bronze model mapping in SOURCE_TO_BRONZE_MODELS. "
            "Add it to the mapping in source_backfill.py and retry.",
            source,
        )
        sys.exit(1)

    bronze_models = SOURCE_TO_BRONZE_MODELS[source]

    logger.info("=" * 60)
    logger.info("SOURCE BACKFILL — %s", source)
    logger.info("Bronze models : %s", ', '.join(bronze_models))
    logger.info("Days back     : %d", days_back)
    logger.info("Data dir      : %s", args.data_dir)
    logger.info("SQLMesh dir   : %s", args.sqlmesh_dir)
    if args.dry_run:
        logger.info("DRY RUN — no actual work will be performed")
    logger.info("=" * 60)

    run_all_stages = not any(stage_flags)
    do_fetch     = run_all_stages or args.fetch_only
    do_transform = run_all_stages or args.transform_only
    do_health    = run_all_stages or args.health_only

    overall_start = time.monotonic()

    if do_fetch:
        ok = run_fetch(source, days_back, args.data_dir, args.dry_run)
        if not ok:
            logger.error("Fetch stage FAILED — aborting")
            sys.exit(1)

    if do_transform:
        ok = run_bronze_transform(bronze_models, args.sqlmesh_dir, args.dry_run)
        if not ok:
            logger.error("Bronze transform stage FAILED — aborting")
            sys.exit(2)

    if do_health:
        ok = run_health_check(bronze_models, args.dry_run)
        if not ok:
            logger.error("Health check FAILED — investigate before moving to the next source")
            sys.exit(3)

    elapsed = time.monotonic() - overall_start
    logger.info("=" * 60)
    logger.info("SOURCE BACKFILL COMPLETE: %s (%.0fs)", source, elapsed)
    logger.info("=" * 60)
    sys.exit(0)


if __name__ == '__main__':
    main()
