#!/usr/bin/env python3
"""Full molecule data pipeline runner.

Feature: 012-dk-data-platform
Description: End-to-end molecule data pipeline (Fetch -> Transform -> Resolve)

Usage:
    python -m ingestion.run_molecule_pipeline
    python -m ingestion.run_molecule_pipeline --skip-fetch
    python -m ingestion.run_molecule_pipeline --skip-transform
"""

import argparse
import logging
import sys
from datetime import datetime
from dk_data.ingestion.utils.database import build_dsn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def run_fetch_phase(sources: list[str] = None, batch_size: int = 100) -> dict:
    """
    Run the data fetch phase.

    Args:
        sources: List of sources to fetch, or None for all
        batch_size: Batch size for fetching

    Returns:
        Result dictionary
    """
    from ingestion.fetch_molecules import fetch_all, fetch_source

    logger.info("=" * 60)
    logger.info("PHASE 1: DATA FETCH")
    logger.info("=" * 60)

    if sources:
        results = {}
        for source in sources:
            results[source] = fetch_source(source, batch_size=batch_size)
        return {
            'status': 'success' if all(r.get('status') == 'success' for r in results.values()) else 'partial',
            'sources': results,
        }
    else:
        return fetch_all(batch_size=batch_size)


def run_transform_phase(layers: list[str] = None) -> dict:
    """
    Run the SQLMesh transformation phase.

    Args:
        layers: List of layers to transform, or None for all

    Returns:
        Result dictionary
    """
    from ingestion.transform_molecules import transform_all_layers, transform_layer

    logger.info("=" * 60)
    logger.info("PHASE 2: DATA TRANSFORMATION")
    logger.info("=" * 60)

    if layers:
        results = {}
        for layer in layers:
            results[layer] = transform_layer(layer)
        return {
            'status': 'success' if all(r.get('status') == 'success' for r in results.values()) else 'partial',
            'layers': results,
        }
    else:
        return transform_all_layers()


def run_resolution_phase() -> dict:
    """
    Run the entity resolution phase.

    Returns:
        Result dictionary
    """
    import psycopg2
    from ingestion.services.molecules.identifier_resolver import IdentifierResolver

    logger.info("=" * 60)
    logger.info("PHASE 3: ENTITY RESOLUTION")
    logger.info("=" * 60)

    try:
        # Get database connection
        conn = psycopg2.connect(build_dsn())

        resolver = IdentifierResolver(conn)

        # Process quarantine queue
        queue = resolver.get_quarantine_queue(limit=100)
        resolved_count = 0
        quarantined_count = len(queue)

        logger.info(f"Found {quarantined_count} molecules in quarantine queue")

        # Log stats but don't auto-resolve (requires manual review)
        conn.close()

        return {
            'status': 'success',
            'quarantined_count': quarantined_count,
            'resolved_count': resolved_count,
        }

    except Exception as e:
        logger.exception(f"Entity resolution phase failed: {e}")
        return {
            'status': 'failed',
            'error': str(e),
        }


def run_full_pipeline(
    skip_fetch: bool = False,
    skip_transform: bool = False,
    skip_resolution: bool = False,
    sources: list[str] = None,
    layers: list[str] = None,
    batch_size: int = 100,
) -> dict:
    """
    Run the full molecule data pipeline.

    Args:
        skip_fetch: Skip the fetch phase
        skip_transform: Skip the transform phase
        skip_resolution: Skip the resolution phase
        sources: Sources to fetch (None for all)
        layers: Layers to transform (None for all)
        batch_size: Batch size for fetching

    Returns:
        Combined results dictionary
    """
    pipeline_start = datetime.now()
    results = {
        'phases': {},
        'status': 'success',
    }

    # Phase 1: Fetch
    if not skip_fetch:
        fetch_result = run_fetch_phase(sources=sources, batch_size=batch_size)
        results['phases']['fetch'] = fetch_result

        if fetch_result.get('status') == 'failed':
            results['status'] = 'failed'
            logger.error("Fetch phase failed, stopping pipeline")
            return results

    # Phase 2: Transform
    if not skip_transform:
        transform_result = run_transform_phase(layers=layers)
        results['phases']['transform'] = transform_result

        if transform_result.get('status') == 'failed':
            results['status'] = 'partial'
            logger.warning("Transform phase had failures")

    # Phase 3: Resolution
    if not skip_resolution:
        resolution_result = run_resolution_phase()
        results['phases']['resolution'] = resolution_result

        if resolution_result.get('status') == 'failed':
            results['status'] = 'partial'
            logger.warning("Resolution phase had failures")

    # Calculate duration
    pipeline_end = datetime.now()
    duration = (pipeline_end - pipeline_start).total_seconds()
    results['duration_seconds'] = duration

    return results


def print_pipeline_summary(results: dict):
    """Print pipeline execution summary."""
    print("\n" + "=" * 60)
    print("MOLECULE PIPELINE SUMMARY")
    print("=" * 60)

    for phase_name, phase_result in results.get('phases', {}).items():
        status = phase_result.get('status', 'unknown')
        status_icon = '✓' if status == 'success' else '⚠' if status == 'partial' else '✗'
        print(f"\n  {status_icon} {phase_name.upper()}")

        if phase_name == 'fetch' and 'sources' in phase_result:
            for source, source_result in phase_result['sources'].items():
                records = source_result.get('records', '-')
                src_status = source_result.get('status', 'unknown')
                src_icon = '✓' if src_status == 'success' else '✗'
                print(f"      {src_icon} {source}: {records} records")

        elif phase_name == 'transform' and 'layers' in phase_result:
            for layer, layer_result in phase_result['layers'].items():
                success = layer_result.get('success_count', 0)
                total = len(layer_result.get('models', {}))
                layer_status = layer_result.get('status', 'unknown')
                layer_icon = '✓' if layer_status == 'success' else '⚠'
                print(f"      {layer_icon} {layer}: {success}/{total} models")

        elif phase_name == 'resolution':
            quarantined = phase_result.get('quarantined_count', 0)
            resolved = phase_result.get('resolved_count', 0)
            print(f"      Quarantined: {quarantined}")
            print(f"      Resolved: {resolved}")

    duration = results.get('duration_seconds', 0)
    overall_status = results.get('status', 'unknown')
    print(f"\n  Overall: {overall_status.upper()}")
    print(f"  Duration: {duration:.1f} seconds")
    print()


def main():
    parser = argparse.ArgumentParser(
        description='Run full molecule data pipeline (Fetch -> Transform -> Resolve)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              Run full pipeline
  %(prog)s --skip-fetch                 Skip fetch, run transform + resolve
  %(prog)s --skip-transform             Skip transform, run fetch + resolve
  %(prog)s --sources chembl pubchem     Fetch only specific sources
  %(prog)s --layers bronze silver       Transform only specific layers
        """
    )

    parser.add_argument(
        '--skip-fetch',
        action='store_true',
        help='Skip the data fetch phase'
    )
    parser.add_argument(
        '--skip-transform',
        action='store_true',
        help='Skip the transformation phase'
    )
    parser.add_argument(
        '--skip-resolution',
        action='store_true',
        help='Skip the entity resolution phase'
    )
    parser.add_argument(
        '--sources',
        nargs='+',
        choices=['chembl', 'pubchem', 'clinicaltrials', 'openfda_labels', 'openfda_faers'],
        help='Specific sources to fetch'
    )
    parser.add_argument(
        '--layers',
        nargs='+',
        choices=['bronze', 'silver', 'gold'],
        help='Specific layers to transform'
    )
    parser.add_argument(
        '--batch-size', '-b',
        type=int,
        default=100,
        help='Batch size for fetching (default: 100)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info(f"Pipeline started at: {datetime.now().isoformat()}")

    # Run pipeline
    results = run_full_pipeline(
        skip_fetch=args.skip_fetch,
        skip_transform=args.skip_transform,
        skip_resolution=args.skip_resolution,
        sources=args.sources,
        layers=args.layers,
        batch_size=args.batch_size,
    )

    # Print summary
    print_pipeline_summary(results)

    logger.info(f"Pipeline completed at: {datetime.now().isoformat()}")

    # Return exit code based on status
    if results.get('status') == 'failed':
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
