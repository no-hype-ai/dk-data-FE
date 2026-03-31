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
        'mol_bronze.pubchem_compounds',
        'mol_bronze.clinical_trials',
        'mol_bronze.openfda_labels',
        'mol_bronze.openfda_faers',
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
    ],
    'ip_gold': [
        'mol_gold.molecule_profile',
        # 015-assessment-dashboard-integration
        'mol_gold.kol_drug_associations',
        'mol_gold.advocacy_groups',
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
        full_command = ['sqlmesh', '-c', str(config_path)] + command

        logger.info(f"Running: {' '.join(full_command)}")

        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={
                **os.environ,
                'SQLMESH_CONFIG': str(config_path),
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


def is_sqlmesh_initialized() -> bool:
    """Check whether SQLMesh state tables exist in the database."""
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
        cur.execute("SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename = '_snapshots')")
        initialized = cur.fetchone()[0]
        conn.close()
        return initialized
    except Exception as e:
        logger.warning(f"Could not check SQLMesh init state: {e}")
        return False


def ensure_sqlmesh_initialized() -> bool:
    """Run SQLMesh plan --auto-apply if state tables are missing.

    Uses --forward-only so historical intervals are not backfilled —
    production sources only have current data, and the config start date
    (2024-01-01) would otherwise trigger a 15-month backfill.

    Returns True if already initialized or plan succeeded, False on failure.
    """
    if is_sqlmesh_initialized():
        return True

    logger.info(
        "SQLMesh environment not initialized (no _snapshots table). "
        "Running plan --auto-apply --forward-only to bootstrap state..."
    )
    result = run_sqlmesh_command(
        ['plan', '--auto-apply', '--forward-only'],
        timeout=600,  # 10 min ceiling for plan
    )
    if result.get('status') == 'success':
        logger.info("SQLMesh plan applied — environment bootstrapped")
        return True

    logger.error(f"SQLMesh plan bootstrap failed: {result.get('error')}")
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

    # Process layers in order: molecule pipeline then IP pipeline
    for layer in ['bronze', 'silver', 'gold', 'ip_bronze', 'ip_silver', 'ip_gold']:
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
        choices=['bronze', 'silver', 'gold', 'ip_bronze', 'ip_silver', 'ip_gold', 'all'],
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
