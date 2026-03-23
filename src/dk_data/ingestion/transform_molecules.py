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
        'mol_bronze.pubchem',
        'mol_bronze.clinicaltrials',
        'mol_bronze.openfda_labels',
        'mol_bronze.faers_events',
        'mol_bronze.drugbank',
    ],
    'silver': [
        # mol_silver.molecules is managed by Xenon onboarding (not SQLMesh) —
        # it has FK references and manual data that can't be replaced by a VIEW
        'mol_silver.bioactivity',
        'mol_silver.molecule_aliases',   # must run before adverse_events (adverse_events JOINs it)
        'mol_silver.drug_labels',
        'mol_silver.adverse_events',     # depends on molecule_aliases
        'mol_silver.clinical_trials',
        'mol_silver.identifier_mappings',
    ],
    'gold': [
        'mol_gold.molecule_profile',
        'mol_gold.safety_signals',
        'mol_gold.lifecycle_stages',
        'mol_gold.lifecycle_evidence',
        'mol_gold.advocacy_sentiment',
        'mol_gold.advocacy_groups',
        'mol_gold.regulatory_timeline',
        'mol_gold.financial_summary',
        'mol_gold.competitive_landscape',
        'mol_gold.company_pipeline',
    ],
    # IP / Patent / Trademark + supplemental bronze models
    'ip_bronze': [
        'mol_bronze.uspto_patents',
        'mol_bronze.uspto_ci',
        'mol_bronze.epo_patents',
        'mol_bronze.uspto_trademarks',
        'mol_bronze.euipo_trademarks',
        'mol_bronze.pubmed',
        'mol_bronze.ema',
        'mol_bronze.hta_decisions',
        'mol_bronze.cochrane_reviews',
        'mol_bronze.sec_edgar',
        'mol_bronze.orcid',
        'mol_bronze.journal_rss',
        'mol_bronze.medical_news',
        'mol_bronze.cms_inpatient',
        'mol_bronze.cms_hospital_info',
        'mol_bronze.cms_cost_reports',
        'mol_bronze.acc_tvc',
        'mol_bronze.hrsa',
        'mol_bronze.pdb_structures',
        'mol_bronze.who_icd',
        'mol_bronze.dailymed',
        'mol_bronze.sider',
        'mol_bronze.bindingdb',
        'mol_bronze.openalex',
        'mol_bronze.uniprot',
        'mol_bronze.orange_book',
        'mol_bronze.purple_book',
        'mol_bronze.who_gho',
        'mol_bronze.ct_gov_indication_stats',
    ],
    'ip_silver': [
        'mol_silver.patents',
        'mol_silver.trademarks',
        'mol_silver.publications',
        'mol_silver.targets',
        'mol_silver.regulatory_decisions',
        'mol_silver.financial_data',
        'mol_silver.news_signals',
        'mol_silver.dailymed_labels',
        'mol_silver.patent_exclusivities',
        'mol_silver.molecule_publications',
        'mol_silver.molecule_targets',
    ],
    'ip_gold': [
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
    import tempfile
    import shutil

    try:
        config_path = get_sqlmesh_config_path()

        # SQLMesh writes logs to {config_dir}/logs/ which may not be writable
        # (e.g. when config is inside site-packages). Copy to a temp dir first.
        tmpdir = tempfile.mkdtemp(prefix='sqlmesh_run_')
        try:
            shutil.copytree(str(config_path.parent), tmpdir, dirs_exist_ok=True)
            os.makedirs(os.path.join(tmpdir, 'logs'), exist_ok=True)
            work_config = os.path.join(tmpdir, 'config.yaml')
            full_command = ['sqlmesh', '--paths', tmpdir] + command
        except Exception as copy_err:
            # Fall back to original path if copy fails
            logger.warning(f"Could not copy SQLMesh config to tmpdir: {copy_err}")
            tmpdir = None
            work_config = str(config_path)
            full_command = ['sqlmesh', '--paths', str(config_path.parent)] + command

        logger.info(f"Running: {' '.join(full_command)}")

        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={
                **os.environ,
                'SQLMESH_CONFIG': work_config,
                'OTEL_SDK_DISABLED': 'true',  # Disable trace exporter to avoid connection errors
            }
        )

        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)

        if result.returncode == 0:
            return {
                'status': 'success',
                'stdout': result.stdout,
                'stderr': result.stderr,
            }
        else:
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


def transform_model(model_name: str) -> dict:
    """
    Run transformation for a specific model.

    Args:
        model_name: Fully qualified model name (e.g., mol_bronze.chembl_molecules)

    Returns:
        Result dictionary
    """
    logger.info(f"Transforming model: {model_name}")

    # Use 'sqlmesh run --select-model' for hot-path transforms.
    # 'plan --auto-apply' re-applies the ENTIRE environment plan, causing cascading failures
    # when unrelated models (e.g. epo_patents) have errors, and leaves stale plan locks.
    # The prod environment is already initialized by the sqlmesh-scheduler; 'run' is sufficient.
    #
    # Pass --start 30 days ago and --end tomorrow to guarantee late-arriving raw records
    # are processed. INCREMENTAL_BY_TIME_RANGE models mark intervals as "complete" in SQLMesh
    # state; without --start, newly inserted raw records in a previously-completed interval
    # (e.g. March 22 records when state tracks "processed through March 23") are silently
    # skipped. The models also have `lookback` set (4 for @weekly, 7 for @daily), which
    # tells SQLMesh to reprocess recent intervals even when they appear complete in state.
    from datetime import date, timedelta
    start_30d = (date.today() - timedelta(days=30)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    result = run_sqlmesh_command([
        'run', '--select-model', model_name,
        '--ignore-cron', '--no-auto-upstream',
        '--start', start_30d,
        '--end', tomorrow,
    ], timeout=180)  # 3-minute max; stale plan lock retries every 30s, fail fast

    if result.get('status') == 'success':
        logger.info(f"Model {model_name} transformed successfully")
    else:
        detail = result.get('stderr') or result.get('stdout') or result.get('error', '')
        logger.error(f"Model {model_name} transformation failed: {result.get('error')} — {detail[:500]}")

    return result


def transform_layer(layer: str) -> dict:
    """
    Run transformations for all models in a layer.

    Args:
        layer: Layer name (bronze, silver, gold)

    Returns:
        Combined results dictionary
    """
    if layer not in LAYER_MODELS:
        return {'status': 'failed', 'error': f'Unknown layer: {layer}'}

    models = LAYER_MODELS[layer]
    results = {}
    success_count = 0
    fail_count = 0

    logger.info(f"Transforming {layer} layer ({len(models)} models)")

    for model_name in models:
        logger.info(f"\n{'-'*40}")
        logger.info(f"Model: {model_name}")
        logger.info(f"{'-'*40}")

        result = transform_model(model_name)
        results[model_name] = result

        if result.get('status') == 'success':
            success_count += 1
        else:
            fail_count += 1

    return {
        'status': 'success' if fail_count == 0 else 'partial',
        'layer': layer,
        'models': results,
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
