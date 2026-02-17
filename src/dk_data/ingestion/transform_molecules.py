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
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
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
    'silver': [
        'mol_silver.molecules_from_bronze',
        'mol_silver.clinical_trials',
        'mol_silver.drug_labels',
        'mol_silver.adverse_events',
    ],
    'gold': [
        'mol_gold.molecule_profiles_agg',
        'mol_gold.safety_signals_agg',
        'mol_gold.trial_analytics_agg',
    ],
    # IP / Patent / Trademark models (014-uspto-euipo-model-datasource)
    'ip_bronze': [
        'bronze.uspto_patents',
        'bronze.uspto_ci',
        'bronze.epo_patents',
        'bronze.uspto_trademarks',
        'bronze.euipo_trademarks',
    ],
    'ip_silver': [
        'silver.patents',
        'silver.trademarks',
    ],
    'ip_gold': [
        'gold.molecule_profile',
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

    result = run_sqlmesh_command(['run', '--select-model', model_name])

    if result.get('status') == 'success':
        logger.info(f"Model {model_name} transformed successfully")
    else:
        logger.error(f"Model {model_name} transformation failed: {result.get('error')}")

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

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate arguments
    if not any([args.layer, args.model, args.plan, args.apply]):
        parser.print_help()
        return 1

    logger.info(f"Started at: {datetime.now().isoformat()}")

    # Execute requested operation
    if args.plan:
        results = run_plan()
    elif args.apply:
        results = run_apply()
    elif args.model:
        results = transform_model(args.model)
    elif args.layer == 'all':
        results = transform_all_layers()
    else:
        results = transform_layer(args.layer)

    # Print summary
    print_summary(results)

    logger.info(f"Completed at: {datetime.now().isoformat()}")

    # Return exit code based on status
    if results.get('status') == 'failed':
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
