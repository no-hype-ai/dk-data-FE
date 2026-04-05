#!/usr/bin/env python3
"""CLI for running molecule data transformations via SQLMesh.

Feature: 012-dk-data-platform
Description: Entry point for molecule data transformation pipeline (Bronze -> Silver -> Gold)

Usage:
    python -m ingestion.transform_molecules --layer bronze
    python -m ingestion.transform_molecules --layer silver
    python -m ingestion.transform_molecules --layer gold
    python -m ingestion.transform_molecules --layer all
    python -m ingestion.transform_molecules --model mol_bronze.chembl_molecules
"""

import argparse
import asyncio
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Observability (013-dk-data-observability T023+T030)
try:
    from dk_data.observability import setup_telemetry, get_tracer
    from dk_data.observability.logging import setup_logging, get_logger
    from dk_data.observability.reporting import report_completion
    _OBS_AVAILABLE = True
except ImportError:
    _OBS_AVAILABLE = False

import logging
logger = logging.getLogger(__name__)


# SQLMesh model definitions by layer
LAYER_MODELS = {
    'bronze': [
        'mol_bronze.chembl_molecules',
        'mol_bronze.openfda_labels',
    ],
    # Silver — molecule entity resolution hub.
    # ORDERING: SQLMesh resolves intra-layer deps from SQL, but the declared list
    # controls which models get selected. molecules_from_bronze must be first so
    # the molecule entity hub exists before alias/bridge tables reference it.
    # molecule_aliases and identifier_mappings are added here because they are
    # foundation tables for all subsequent HCS silver cross-domain joins:
    #   hcs_silver.part_d_prescribing, drug_utilization, open_payments_drug_linkage
    #   all JOIN mol_silver.molecule_aliases to resolve drug names → molecule_ids.
    'silver': [
        'mol_silver.molecules_from_bronze',   # entity hub — must be first
        'mol_silver.targets',                  # protein targets (no mol dep)
        'mol_silver.drug_labels',              # needs molecules
        'mol_silver.clinical_trials',          # needs molecules
        'mol_silver.adverse_events',           # needs molecules + identifier_mappings
        'mol_silver.molecule_aliases',         # needs molecules+drug_labels+clinical_trials
                                               # critical: HCS silver joins this for drug name resolution
        'mol_silver.identifier_mappings',      # needs molecules+targets+drug_labels
                                               # critical: adverse_events, binding lookups join this
    ],
    'gold': [
        'mol_gold.molecule_profiles_agg',
        'mol_gold.safety_signals_agg',
        'mol_gold.trial_analytics_agg',
        # 015-assessment-dashboard-integration
        'mol_gold.kol_profiles',
        'mol_gold.kol_network',
        'mol_gold.advocacy_sentiment',
        'mol_gold.trial_outcomes',
        'mol_gold.regulatory_timeline',
        'mol_gold.financial_summary',
    ],
    # IP / Patent / Trademark models (014-uspto-euipo-model-datasource)
    # These are all hcs_bronze + IP mol_bronze — fully independent of silver,
    # so they run in a parallel job at 06:30 alongside mol_bronze at 06:00.
    'ip_bronze': [
        'mol_bronze.uspto_patents',
        'mol_bronze.uspto_ci',
        'mol_bronze.epo_patents',
        'mol_bronze.uspto_trademarks',
        'mol_bronze.euipo_trademarks',
        'mol_bronze.euipo_designs',
        # 015-assessment-dashboard-integration
        'mol_bronze.pubmed',
        'mol_bronze.ema',
        'mol_bronze.hta_decisions',
        'mol_bronze.cochrane_reviews',
        'mol_bronze.sec_edgar',
        'mol_bronze.orcid',
        'mol_bronze.journal_rss',
        'mol_bronze.medical_news',
        'hcs_bronze.cms_inpatient',
        'hcs_bronze.cms_hospital_info',
        'hcs_bronze.cms_cost_reports',
        'hcs_bronze.acc_tvc',
        'hcs_bronze.hrsa',
        'mol_bronze.pdb_structures',
        'mol_bronze.who_icd',
    ],
    # ip_silver runs AFTER both silver AND ip_bronze finish.
    # hcpcs_molecule_bridge reads hcs_bronze.cms_dme_puf/lab_services/imaging_puf (ip_bronze)
    # AND mol_silver.molecule_aliases (silver) — it bridges both domains.
    # ndc_molecule_bridge and rxnorm_concepts also need mol_silver.molecule_aliases.
    'ip_silver': [
        'mol_silver.patents',
        'mol_silver.trademarks',
        # 015-assessment-dashboard-integration
        'mol_silver.publications',
        'mol_silver.regulatory_decisions',
        'mol_silver.financial_data',
        'mol_silver.researchers',
        'mol_silver.news_signals',
        'mol_silver.healthcare_facilities',
        'mol_silver.icd_codes',
        # Cross-domain bridge tables (need mol_silver.molecule_aliases from silver layer):
        'mol_silver.ndc_molecule_bridge',      # NDC → molecule_id (used by hcs_silver.open_payments)
        'mol_silver.rxnorm_concepts',           # RxNorm CUIs → molecule_id
        'mol_silver.hcpcs_molecule_bridge',     # HCPCS codes → molecule_id (needs hcs_bronze + molecule_aliases)
        'mol_silver.trademark_status_changes',  # Trademark audit trail with mol linkage (issue #171 M5)
        # Moved from hcs_silver (09:00): depends on ndc_molecule_bridge above — must run after it.
        'hcs_silver.open_payments_drug_linkage',  # hcs_bronze + mol_silver.ndc_molecule_bridge
    ],
    # ind_gold — IND domain gold layer (issue #171 H1).
    # Runs after ip_silver finishes (ind_silver.icd11_ontology is an upstream dep).
    'ind_gold': [
        'ind_gold.indication_catalog',
    ],
    'ip_gold': [
        'mol_gold.molecule_profile',
        # 015-assessment-dashboard-integration
        'mol_gold.kol_drug_associations',
        'mol_gold.advocacy_groups',
    ],
    # mol_gold_ext — 6 mol_gold models not in gold/ip_gold layers.
    # Runs at 14:00 UTC (after ip_gold 13:00 + mol_silver_ext 11:00).
    'mol_gold_ext': [
        'mol_gold.safety_signals',
        'mol_gold.lifecycle_stages',
        'mol_gold.lifecycle_evidence',
        'mol_gold.company_pipeline',
        'mol_gold.competitive_landscape',
        'mol_gold.market_summary',
    ],
    # mart — data mart + scoring + targeting (all write to hcs_gold schema).
    # Runs at 15:30 UTC (after cms-gold-refresh 14:30 + mol_gold_ext 14:00).
    # mart models read from staging.* (legacy TAVR) and hcs_gold.*
    'mart': [
        'hcs_gold.dim_hospital',
        'hcs_gold.fact_financial_metrics',
        'hcs_gold.fact_tavr_program',
        'hcs_gold.score_factors',
        'hcs_gold.target_scores',
        'hcs_gold.targeting_scores',
        'hcs_gold.targeting_summary',
    ],
    # mol_bronze_ext — 35 mol_bronze models not covered by bronze/ip_bronze layers.
    # Runs at 07:00 UTC in parallel with hcs_bronze (both after ip_bronze 06:30).
    # Includes vocabulary (rxnorm, pharmgkb, bindingdb), FDA (orange_book, fda_drugs,
    # fda_ndc, fda_rems), literature (europepmc, nih_reporter), and clinical (clinicaltrials).
    'mol_bronze_ext': [
        # Vocabulary / reference
        'mol_bronze.rxnorm',
        'mol_bronze.pharmgkb',
        'mol_bronze.bindingdb',
        'mol_bronze.sider',
        'mol_bronze.tdc_admet',
        'mol_bronze.ttd',
        'mol_bronze.uniprot',
        'mol_bronze.pubchem',
        'mol_bronze.cdc_vaccines',
        'mol_bronze.imgt',
        'mol_bronze.kegg_drug',
        'mol_bronze.who_inn',
        'mol_bronze.who_gho',
        'mol_bronze.purple_book',
        'mol_bronze.reactome',
        # FDA / regulatory
        'mol_bronze.orange_book',
        'mol_bronze.fda_drugs',
        'mol_bronze.trademark_status_history',
        'mol_bronze.fda_ndc',
        'mol_bronze.fda_rems',
        'mol_bronze.nice_hta',
        'mol_bronze.cms_coverage',
        'mol_bronze.ema_regulatory',
        # Literature / clinical
        'mol_bronze.europepmc',
        'mol_bronze.nih_reporter',
        'mol_bronze.clinicaltrials',
        'mol_bronze.ct_gov_indication_stats',
        # Drug data
        'mol_bronze.drugbank',
        'mol_bronze.dailymed',
        'mol_bronze.chembl_activities',
        # CMS cross-domain
        'mol_bronze.cms_medicare',
        'mol_bronze.cms_open_payments',
        'mol_bronze.npi_registry',
        # Bio / omics
        'mol_bronze.openalex',
        'mol_bronze.faers_events',
        'mol_bronze.websearch',
    ],
    # HCS bronze — all 53 hcs_bronze.* models (019-cms-puf-platform-reconciliation).
    # Runs at 07:00 UTC (after ip_bronze at 06:30 which covers 5 hcs_bronze models).
    # SQLMesh is idempotent: models already current from ip_bronze are skipped.
    'hcs_bronze': [
        'hcs_bronze.acc_tvc',
        'hcs_bronze.cms_care_compare',
        'hcs_bronze.cms_chow',
        'hcs_bronze.cms_chronic_conditions',
        'hcs_bronze.cms_claim_type_puf',
        'hcs_bronze.cms_cost_reports',
        'hcs_bronze.cms_cost_reports_puf',
        'hcs_bronze.cms_cost_reports_puf_lines',
        'hcs_bronze.cms_ddinter',
        'hcs_bronze.cms_dme_puf',
        'hcs_bronze.cms_dmepos',
        'hcs_bronze.cms_dual_eligible',
        'hcs_bronze.cms_enrollment_puf',
        'hcs_bronze.cms_formulary',
        'hcs_bronze.cms_geographic_variation',
        'hcs_bronze.cms_hcris',
        'hcs_bronze.cms_home_health',
        'hcs_bronze.cms_hospice_puf',
        'hcs_bronze.cms_hospital_affiliation',
        'hcs_bronze.cms_hospital_general_info',
        'hcs_bronze.cms_hospital_info',
        'hcs_bronze.cms_hospital_quality',
        'hcs_bronze.cms_imaging_puf',
        'hcs_bronze.cms_inpatient',
        'hcs_bronze.cms_inpatient_puf',
        'hcs_bronze.cms_lab_services',
        'hcs_bronze.cms_magnet',
        'hcs_bronze.cms_medicaid_drug_spending',
        'hcs_bronze.cms_medicare_advantage',
        'hcs_bronze.cms_mental_health_puf',
        'hcs_bronze.cms_ndc',
        'hcs_bronze.cms_nppes',
        'hcs_bronze.cms_nucc',
        'hcs_bronze.cms_open_payments',
        'hcs_bronze.cms_opioid_puf',
        'hcs_bronze.cms_ordering_providers',
        'hcs_bronze.cms_outpatient_puf',
        'hcs_bronze.cms_part_b_spending',
        'hcs_bronze.cms_part_d_prescriber',
        'hcs_bronze.cms_part_d_spending',
        'hcs_bronze.cms_pecos',
        'hcs_bronze.cms_physician_puf',
        'hcs_bronze.cms_physician_puf_services',
        'hcs_bronze.cms_pos',
        'hcs_bronze.cms_post_acute',
        'hcs_bronze.cms_rbcs',
        'hcs_bronze.cms_referring_providers',
        'hcs_bronze.cms_snf_puf',
        'hcs_bronze.cms_stabilis',
        'hcs_bronze.cms_telehealth_puf',
        'hcs_bronze.cms_usp',
        'hcs_bronze.cms_utilization_puf',
        'hcs_bronze.hrsa',
    ],
    # ind_bronze — ICD-11 codes (reads mol_bronze.who_icd from ip_bronze at 06:30).
    # Runs at 07:30 UTC (after ip_bronze 06:30).
    'ind_bronze': [
        'ind_bronze.icd11_codes',
    ],
    # ind_silver — ICD-11 ontology (reads ind_bronze.icd11_codes).
    # Runs at 08:30 UTC (after ind_bronze 07:30).
    'ind_silver': [
        'ind_silver.icd11_ontology',
    ],
    # mol_silver_ext — 44 mol_silver models not covered by silver/ip_silver layers.
    # Runs at 11:00 UTC — after mol_silver (08:00), mol_bronze_ext (07:00), ip_silver (10:30).
    # Many depend on mol_silver.molecules (in this layer), mol_silver.molecule_aliases (silver),
    # and mol_bronze_ext models (drugbank, pubchem, pharmgkb, etc.).
    # SQLMesh resolves intra-layer deps automatically.
    'mol_silver_ext': [
        # Entity resolution (depends on mol_bronze.pubchem, drugbank, chembl)
        'mol_silver.molecules',
        'mol_silver.drug_synonyms',
        'mol_silver.molecule_targets',
        'mol_silver.molecule_publications',
        # Drug pharmacology & properties
        'mol_silver.drugbank',
        'mol_silver.admet_properties',
        'mol_silver.drug_pharmacology',
        'mol_silver.binding_affinities',
        'mol_silver.bioactivity',
        'mol_silver.side_effects',
        'mol_silver.chembl',
        'mol_silver.pathways',
        'mol_silver.proteins',
        'mol_silver.protein_targets',
        'mol_silver.protein_structures',
        # Clinical data
        'mol_silver.pubmed_articles',
        'mol_silver.cochrane_reviews',
        'mol_silver.research_grants',
        'mol_silver.publication_evidence',
        'mol_silver.ct_gov_indication_stats',
        # FDA / regulatory
        'mol_silver.orange_book',
        'mol_silver.fda_drugs',
        'mol_silver.ema',
        'mol_silver.ema_regulatory',
        'mol_silver.dailymed_labels',
        'mol_silver.rems_programs',
        'mol_silver.patent_exclusivities',
        'mol_silver.regulatory_milestones',
        # Indication / epidemiology
        'mol_silver.indication_ontology',
        'mol_silver.indication_epidemiology',
        'mol_silver.indication_revenue',
        'mol_silver.icd10_indicator_mapping',
        # HCS-adjacent
        'mol_silver.physician_payments',
        'mol_silver.physician_profiles',
        'mol_silver.drug_spending',
        # Vocabulary
        'mol_silver.pharmacogenomics',
        'mol_silver.imgt',
        'mol_silver.cdc_vaccines',
        'mol_silver.who_inn_names',
        'mol_silver.pubchem',
        'mol_silver.ttd',
        # Misc / enrichment
        'mol_silver.company_financials',
        'mol_silver.journal_rss',
        'mol_silver.web_content',
    ],
    # HCS silver — 9 of 10 hcs_silver.* models (019-cms-puf-platform-reconciliation).
    # Runs at 09:00 UTC — after hcs_bronze (07:00) AND mol_silver (08:00) complete.
    # Requires mol_silver.molecule_aliases for drug name resolution joins.
    # NOTE: open_payments_drug_linkage is in ip_silver (10:30), not here,
    #       because it depends on mol_silver.ndc_molecule_bridge which ip_silver builds.
    'hcs_silver': [
        'hcs_silver.ref_nucc_taxonomy',          # reference — no upstream dep on mol_silver
        'hcs_silver.geographic_health',           # hcs_bronze only
        'hcs_silver.healthcare_facilities',       # hcs_bronze only
        'hcs_silver.cms_facility_profile',        # hcs_bronze only
        'hcs_silver.facility_profile',            # hcs_bronze only
        'hcs_silver.provider_profile',            # hcs_bronze only
        'hcs_silver.cms_drug_market',             # hcs_bronze (part_d/part_b)
        'hcs_silver.drug_utilization',            # hcs_bronze + mol_silver.molecule_aliases
        'hcs_silver.part_d_prescribing',          # hcs_bronze + mol_silver.molecule_aliases
    ],
}


def get_sqlmesh_config_path() -> Path:
    """Get the path to SQLMesh configuration."""
    # Check for SQLMESH_CONFIG environment variable first
    config_env = os.getenv('SQLMESH_CONFIG')
    if config_env:
        return Path(config_env)

    # Default to project location
    default_paths = [
        Path(__file__).parent.parent / 'sqlmesh' / 'config.yaml',
        Path('/app/sqlmesh/config.yaml'),
        Path('./sqlmesh/config.yaml'),
    ]

    for path in default_paths:
        if path.exists():
            return path

    raise FileNotFoundError("SQLMesh config.yaml not found")


def run_sqlmesh_command(command: list[str], timeout: int = 3600) -> dict:
    """
    Run a SQLMesh command.

    Args:
        command: Command list to execute
        timeout: Command timeout in seconds

    Returns:
        Result dictionary with status, stdout, stderr
    """
    try:
        config_path = get_sqlmesh_config_path()
        # SQLMesh --paths expects the project directory, not the config.yaml file itself
        project_dir = str(config_path.parent)
        full_command = ['sqlmesh', '--paths', project_dir, '--log-file-dir', '/tmp/sqlmesh-logs'] + command

        logger.info(f"Running: {' '.join(full_command)}")

        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=project_dir,  # run from project dir so SQLMesh creates logs/ there (writable volumeMount)
            env={
                **os.environ,
                'SQLMESH_CONFIG': str(config_path),
                # Point HOME to /tmp so SQLMesh analytics (~/.sqlmesh) doesn't hit read-only FS.
                # The container user home dir is read-only (readOnlyRootFilesystem: true).
                'HOME': '/tmp',
            }
        )

        if result.returncode == 0:
            return {
                'status': 'success',
                'stdout': result.stdout,
                'stderr': result.stderr,
            }
        else:
            # Always surface stderr so errors are visible in pod logs
            if result.stderr:
                logger.error(f"SQLMesh stderr: {result.stderr[:3000]}")
            if result.stdout:
                logger.error(f"SQLMesh stdout: {result.stdout[:1000]}")
            return {
                'status': 'failed',
                'stdout': result.stdout,
                'stderr': result.stderr,
                'error': f"Exit code: {result.returncode}",
            }

    except subprocess.TimeoutExpired:
        return {
            'status': 'failed',
            'error': f"Command timed out after {timeout} seconds",
        }
    except FileNotFoundError as e:
        return {
            'status': 'failed',
            'error': str(e),
        }
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e),
        }


def _sqlmesh_has_state_tables() -> bool:
    """Check if SQLMesh state tables exist (migrate has been run)."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            dbname=os.getenv("POSTGRES_DB", "dk_data"),
        )
        cur = conn.cursor()
        cur.execute("SELECT EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='sqlmesh' AND tablename='_snapshots')")
        result = bool(cur.fetchone()[0])
        conn.close()
        return result
    except Exception as e:
        logger.warning(f"Could not check SQLMesh state tables: {e}")
        return False


def is_sqlmesh_initialized() -> bool:
    """Check whether SQLMesh state tables AND a 'prod' environment exist.

    State tables existing (migrate ran) is not enough — sqlmesh run also
    requires a 'prod' environment entry in sqlmesh._environments, which is
    only created by running sqlmesh plan.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            dbname=os.getenv("POSTGRES_DB", "dk_data"),
        )
        cur = conn.cursor()
        cur.execute("SELECT EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='sqlmesh' AND tablename='_snapshots')")
        has_tables = bool(cur.fetchone()[0])
        if not has_tables:
            conn.close()
            return False
        cur.execute("SELECT EXISTS(SELECT 1 FROM sqlmesh._environments WHERE name = 'prod')")
        has_env = bool(cur.fetchone()[0])
        conn.close()
        return has_env
    except Exception as e:
        logger.warning(f"Could not check SQLMesh init state: {e}")
        return False


def ensure_sqlmesh_initialized() -> bool:
    """Ensure SQLMesh state tables exist and 'prod' environment is registered.

    Two-step bootstrap:
    1. `sqlmesh migrate` — creates sqlmesh schema and state tables
       (_snapshots, _environments, _intervals, _versions, etc.).
       Idempotent; safe to run on an already-migrated DB.
    2. `sqlmesh plan --auto-apply --skip-backfill` — registers all models
       in _snapshots and creates the 'prod' environment entry in
       _environments. Without this, `sqlmesh run` exits with
       "Environment 'prod' was not found."

    Note: `plan` variants fail on a completely fresh DB (before migrate).
    Always run migrate first, then plan.

    Returns True if already initialized or bootstrap succeeded, False on failure.
    """
    if is_sqlmesh_initialized():
        return True

    # Step 1: ensure state tables exist
    if not _sqlmesh_has_state_tables():
        logger.info(
            "SQLMesh state tables missing. Running 'sqlmesh migrate' to bootstrap..."
        )
        result = run_sqlmesh_command(['migrate'], timeout=120)
        if result.get('status') != 'success':
            logger.error(f"SQLMesh migrate failed: {result.get('error')}")
            return False
        logger.info("SQLMesh migrate complete — state tables created")

    # Step 2: register models and create the prod environment
    logger.info(
        "SQLMesh 'prod' environment not found. "
        "Running 'sqlmesh plan --auto-apply --skip-backfill' to register models..."
    )
    result = run_sqlmesh_command(
        ['plan', '--auto-apply', '--skip-backfill'],
        timeout=600,
    )
    if result.get('status') == 'success':
        logger.info("SQLMesh plan complete — prod environment registered")
        return True

    logger.error(f"SQLMesh plan failed: {result.get('error')}")
    return False


def transform_model(model_name: str) -> dict:
    """
    Run transformation for a specific model.

    Args:
        model_name: Fully qualified model name (e.g., mol_bronze.chembl_molecules)

    Returns:
        Result dictionary
    """
    logger.info(f"Transforming model: {model_name}")

    result = run_sqlmesh_command(['run', '--select-model', model_name])

    if result.get('status') == 'success':
        logger.info(f"Model {model_name} transformed successfully")
    else:
        logger.error(f"Model {model_name} transformation failed: {result.get('error')}")

    return result


def transform_layer(layer: str) -> dict:
    """
    Run transformations for all models in a layer as a single SQLMesh invocation.

    Batching all models in one `sqlmesh run` call (via multiple --select-model
    flags) is far more efficient than 51 separate subprocess calls: one DB
    connection, one config load, and SQLMesh handles internal concurrency.

    Args:
        layer: Layer name (bronze, silver, gold, ip_bronze, ip_silver, ip_gold)

    Returns:
        Combined results dictionary
    """
    if layer not in LAYER_MODELS:
        return {'status': 'failed', 'error': f'Unknown layer: {layer}'}

    models = LAYER_MODELS[layer]
    logger.info(f"Transforming {layer} layer ({len(models)} models) in single sqlmesh run")

    # Build one command selecting all models in this layer
    cmd = ['run']
    for model_name in models:
        cmd.extend(['--select-model', model_name])

    result = run_sqlmesh_command(cmd)

    success_count = len(models) if result.get('status') == 'success' else 0
    fail_count = 0 if result.get('status') == 'success' else len(models)

    if result.get('status') == 'success':
        logger.info(f"Layer {layer}: all {len(models)} models complete")
    else:
        logger.error(f"Layer {layer} failed: {result.get('error')}")

    return {
        'status': result.get('status', 'failed'),
        'layer': layer,
        'models': {m: result for m in models},
        'success_count': success_count,
        'fail_count': fail_count,
    }


def transform_all_layers() -> dict:
    """
    Run transformations for all layers in order.

    Returns:
        Combined results dictionary
    """
    all_results = {}
    total_success = 0
    total_fail = 0

    # Always run plan --auto-apply --skip-backfill before the first run so new
    # models added to the codebase are registered in SQLMesh's _snapshots table.
    # Without this, sqlmesh run silently skips models not yet in state.
    # --skip-backfill avoids a 15-month data backfill while still registering new models.
    logger.info("Running sqlmesh plan --auto-apply --skip-backfill to register new models...")
    plan_result = run_sqlmesh_command(
        ['plan', '--auto-apply', '--skip-backfill'],
        timeout=600,
    )
    if plan_result.get('status') != 'success':
        logger.warning(
            "sqlmesh plan --auto-apply failed (non-fatal): %s",
            plan_result.get('error', 'unknown error'),
        )

    # Full pipeline dependency sequence (UTC schedule when run as individual CronJobs):
    # 06:00 bronze → 06:30 ip_bronze → 07:00 hcs_bronze+mol_bronze_ext → 07:30 ind_bronze
    # → 08:00 silver → 08:30 ind_silver → 09:00 hcs_silver → 10:30 ip_silver
    # → 11:00 mol_silver_ext → 12:00 gold → 13:00 ip_gold → 14:00 mol_gold_ext
    # → 14:30 cms-gold-refresh → 15:30 mart
    for layer in ['bronze', 'ip_bronze', 'mol_bronze_ext', 'hcs_bronze',
                  'ind_bronze', 'silver', 'ind_silver', 'hcs_silver',
                  'ip_silver', 'mol_silver_ext', 'gold', 'ip_gold',
                  'mol_gold_ext', 'mart']:
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing {layer.upper()} layer")
        logger.info(f"{'='*60}")

        result = transform_layer(layer)
        all_results[layer] = result

        total_success += result.get('success_count', 0)
        total_fail += result.get('fail_count', 0)

        # Stop if layer failed completely
        if result.get('status') == 'failed':
            logger.error(f"Layer {layer} failed completely, stopping pipeline")
            break

    return {
        'status': 'success' if total_fail == 0 else 'partial',
        'layers': all_results,
        'success_count': total_success,
        'fail_count': total_fail,
    }


def run_plan() -> dict:
    """
    Run SQLMesh plan to preview changes.

    Returns:
        Result dictionary
    """
    logger.info("Running SQLMesh plan...")
    return run_sqlmesh_command(['plan', '--no-prompts'])


def run_apply() -> dict:
    """
    Apply SQLMesh changes (run all pending transformations).

    Returns:
        Result dictionary
    """
    logger.info("Applying SQLMesh transformations...")
    return run_sqlmesh_command(['run'])


def print_summary(results: dict):
    """Print transformation summary."""
    print("\n" + "=" * 60)
    print("MOLECULE TRANSFORMATION SUMMARY")
    print("=" * 60)

    if 'layers' in results:
        for layer, layer_result in results['layers'].items():
            status = layer_result.get('status', 'unknown')
            status_icon = '✓' if status == 'success' else '⚠' if status == 'partial' else '✗'
            models_count = len(layer_result.get('models', {}))
            success = layer_result.get('success_count', 0)
            layer_result.get('fail_count', 0)
            print(f"\n  {status_icon} {layer.upper():10} ({success}/{models_count} models)")

            for model_name, model_result in layer_result.get('models', {}).items():
                model_status = model_result.get('status', 'unknown')
                model_icon = '✓' if model_status == 'success' else '✗'
                short_name = model_name.split('.')[-1]
                print(f"      {model_icon} {short_name}")

        print(f"\nTotal: {results.get('success_count', 0)} succeeded, {results.get('fail_count', 0)} failed")

    elif 'models' in results:
        layer = results.get('layer', 'unknown')
        print(f"\n  Layer: {layer.upper()}")

        for model_name, model_result in results['models'].items():
            model_status = model_result.get('status', 'unknown')
            model_icon = '✓' if model_status == 'success' else '✗'
            short_name = model_name.split('.')[-1]
            print(f"      {model_icon} {short_name}")

        print(f"\nTotal: {results.get('success_count', 0)} succeeded, {results.get('fail_count', 0)} failed")

    else:
        status = results.get('status', 'unknown')
        print(f"  Status: {status}")

        if results.get('stdout'):
            print(f"\n  Output:\n{results['stdout'][:1000]}")

        if results.get('error'):
            print(f"\n  Error: {results['error']}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description='Run molecule data transformations via SQLMesh',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --layer bronze              Transform bronze layer models
  %(prog)s --layer silver              Transform silver layer models
  %(prog)s --layer gold                Transform gold layer models
  %(prog)s --layer all                 Transform all layers (bronze->silver->gold)
  %(prog)s --model mol_bronze.chembl   Transform specific model
  %(prog)s --plan                      Preview pending changes
  %(prog)s --apply                     Apply all pending transformations
        """
    )

    parser.add_argument(
        '--layer', '-l',
        choices=['bronze', 'silver', 'gold', 'ip_bronze', 'ip_silver', 'ip_gold',
                 'hcs_bronze', 'hcs_silver',
                 'mol_bronze_ext', 'mol_silver_ext', 'mol_gold_ext',
                 'ind_bronze', 'ind_silver', 'mart', 'all'],
        help='Layer to transform'
    )
    parser.add_argument(
        '--model', '-m',
        help='Specific model to transform (fully qualified name)'
    )
    parser.add_argument(
        '--plan', '-p',
        action='store_true',
        help='Preview pending changes (SQLMesh plan)'
    )
    parser.add_argument(
        '--apply', '-a',
        action='store_true',
        help='Apply all pending transformations'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Configure observability (013-dk-data-observability)
    global logger
    job_name = f"mol-transform-{args.layer}" if args.layer else "mol-transform"
    if _OBS_AVAILABLE:
        setup_telemetry("mol-transform")
        setup_logging("mol-transform")
        logger = get_logger(__name__)
    elif args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate arguments
    if not any([args.layer, args.model, args.plan, args.apply]):
        parser.print_help()
        return 1

    logger.info(f"Started at: {datetime.now().isoformat()}")

    start_time = time.monotonic()
    status = "failure"
    records = 0

    try:
        tracer = get_tracer(__name__) if _OBS_AVAILABLE else None

        def _do_transform():
            # Ensure SQLMesh state is bootstrapped before any run/transform.
            # Runs plan --auto-apply --forward-only on first ever execution so
            # sqlmesh run doesn't exit 2 with "no environments found".
            if not args.plan:
                if not ensure_sqlmesh_initialized():
                    return {'status': 'failed', 'error': 'SQLMesh initialization failed', 'success_count': 0, 'fail_count': 1}

            if args.plan:
                return run_plan()
            elif args.apply:
                return run_apply()
            elif args.model:
                return transform_model(args.model)
            elif args.layer == 'all':
                return transform_all_layers()
            else:
                return transform_layer(args.layer)

        if tracer:
            with tracer.start_as_current_span(f"{job_name}-execution") as span:
                span.set_attribute("layer", args.layer or args.model or "plan/apply")
                results = _do_transform()
                records = results.get('success_count', 0)
                span.set_attribute("records_fetched", records)
        else:
            results = _do_transform()
            records = results.get('success_count', 0)

        # Print summary
        print_summary(results)

        logger.info(f"Completed at: {datetime.now().isoformat()}")

        if results.get('status') == 'failed':
            return 1
        status = "success"
        return 0

    except Exception as e:
        logger.error(f"Transform failed: {e}")
        return 1

    finally:
        duration = time.monotonic() - start_time
        if _OBS_AVAILABLE:
            try:
                asyncio.run(report_completion(
                    job_name=job_name,
                    status=status,
                    duration_seconds=duration,
                    records_processed=records,
                ))
            except Exception as e:
                logger.warning(f"Failed to report completion: {e}")


if __name__ == '__main__':
    sys.exit(main())
