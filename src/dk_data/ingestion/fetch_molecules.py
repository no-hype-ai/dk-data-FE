#!/usr/bin/env python3
"""CLI for fetching molecule data from external sources.

Feature: 012-dk-data-platform
Description: Entry point for molecule data ingestion using data_platform services.
             Uses the RawIngestionService from trials-predictor for dynamic source handling.

Usage:
    python -m ingestion.fetch_molecules --source chembl
    python -m ingestion.fetch_molecules --source all
    python -m ingestion.fetch_molecules --list
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def get_db_config() -> dict:
    """Get database configuration from environment variables."""
    return {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('POSTGRES_PORT', '5432')),
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', 'postgres'),
        'database': os.getenv('POSTGRES_DB', 'edwards_tavr'),
    }


def get_connection_string() -> str:
    """Get PostgreSQL connection string."""
    config = get_db_config()
    return f"postgresql://{config['user']}:{config['password']}@{config['host']}:{config['port']}/{config['database']}"


async def list_sources():
    """Print available molecule data sources."""
    try:
        from services.data_platform import REFRESH_SCHEDULE

        print("\nAvailable Molecule Data Sources:")
        print("=" * 70)
        print(f"  {'Source':<20} {'Refresh':<15} {'Status'}")
        print(f"  {'-'*20} {'-'*15} {'-'*30}")

        for source_name, schedule in REFRESH_SCHEDULE.items():
            print(f"  {source_name:<20} {schedule:<15} Available")

        print()
    except ImportError as e:
        logger.error(f"Could not import data_platform services: {e}")
        print("\nFallback - Available sources from external_apis:")
        print("  - chembl")
        print("  - clinicaltrials")
        print("  - openfda")
        print("  - openalex")
        print("  - uniprot")
        print()


async def fetch_source(source: str, batch_size: int = 100) -> dict:
    """
    Fetch data from a single molecule source using RawIngestionService.

    Args:
        source: Source name
        batch_size: Number of records per batch

    Returns:
        Fetch result dictionary
    """
    try:
        from services.data_platform import (
            ChEMBLIngestion,
            PubChemIngestion,
            ClinicalTrialsIngestion,
            OpenFDAIngestion,
            UniProtIngestion,
            OpenAlexIngestion,
        )

        # Map source names to ingestion classes
        ingestion_classes = {
            'chembl': ChEMBLIngestion,
            'pubchem': PubChemIngestion,
            'clinicaltrials': ClinicalTrialsIngestion,
            'openfda': OpenFDAIngestion,
            'uniprot': UniProtIngestion,
            'openalex': OpenAlexIngestion,
        }

        if source not in ingestion_classes:
            return {'status': 'failed', 'error': f'Unknown source: {source}', 'source': source}

        logger.info(f"Starting {source} fetch using data_platform services")
        db_url = get_connection_string()

        ingestion_class = ingestion_classes[source]
        service = ingestion_class(db_url)

        # Run ingestion
        result = await service.ingest(batch_size=batch_size)

        logger.info(f"Fetched {result.get('records', 0)} records from {source}")
        return {
            'status': 'success',
            'records': result.get('records', 0),
            'source': source,
        }

    except ImportError:
        # Fall back to external_apis clients
        return await fetch_source_with_clients(source, batch_size)

    except Exception as e:
        logger.exception(f"{source} fetch failed: {e}")
        return {'status': 'failed', 'error': str(e), 'source': source}


async def fetch_source_with_clients(source: str, batch_size: int = 100) -> dict:
    """
    Fallback: Fetch using external_apis clients directly.

    Args:
        source: Source name
        batch_size: Number of records per batch

    Returns:
        Fetch result dictionary
    """
    logger.info(f"Using external_apis clients for {source}")

    try:
        if source == 'chembl':
            from services.external_apis.chembl_client import ChEMBLClient
            async with ChEMBLClient() as client:
                molecules = await client.get_approved_drugs(limit=batch_size)
                return {'status': 'success', 'records': len(molecules), 'source': source}

        elif source == 'clinicaltrials':
            from services.external_apis.clinicaltrials_client import ClinicalTrialsClient
            async with ClinicalTrialsClient() as client:
                trials = await client.search_trials(query="drug", max_results=batch_size)
                return {'status': 'success', 'records': len(trials), 'source': source}

        elif source == 'openfda':
            from services.external_apis.openfda_client import OpenFDAClient
            async with OpenFDAClient() as client:
                labels = await client.search_drug_labels(limit=batch_size)
                return {'status': 'success', 'records': len(labels), 'source': source}

        elif source == 'openalex':
            from services.external_apis.openalex_client import OpenAlexClient
            async with OpenAlexClient() as client:
                works = await client.search_works(query="pharmaceutical", per_page=batch_size)
                return {'status': 'success', 'records': len(works), 'source': source}

        elif source == 'uniprot':
            from services.external_apis.uniprot_client import UniProtClient
            async with UniProtClient() as client:
                proteins = await client.search_proteins(query="drug target", limit=batch_size)
                return {'status': 'success', 'records': len(proteins), 'source': source}

        else:
            return {'status': 'failed', 'error': f'No client for source: {source}', 'source': source}

    except Exception as e:
        logger.exception(f"{source} fetch failed: {e}")
        return {'status': 'failed', 'error': str(e), 'source': source}


async def fetch_all(batch_size: int = 100) -> dict:
    """
    Fetch data from all active molecule sources.

    Args:
        batch_size: Number of records per batch

    Returns:
        Combined results dictionary
    """
    sources = ['chembl', 'pubchem', 'clinicaltrials', 'openfda', 'uniprot', 'openalex']

    try:
        from services.data_platform import REFRESH_SCHEDULE
        sources = list(REFRESH_SCHEDULE.keys())
    except ImportError:
        pass

    results = {}
    success_count = 0
    fail_count = 0

    logger.info(f"Fetching from {len(sources)} sources")

    for source in sources:
        logger.info(f"\n{'='*60}")
        logger.info(f"Fetching: {source}")
        logger.info(f"{'='*60}")

        result = await fetch_source(source, batch_size=batch_size)
        results[source] = result

        if result.get('status') == 'success':
            success_count += 1
            logger.info(f"SUCCESS: {source} - {result.get('records', 0)} records")
        else:
            fail_count += 1
            logger.error(f"FAILED: {source} - {result.get('error', 'Unknown error')}")

    return {
        'status': 'success' if fail_count == 0 else 'partial',
        'sources': results,
        'success_count': success_count,
        'fail_count': fail_count,
    }


def print_summary(results: dict):
    """Print fetch summary."""
    print("\n" + "=" * 60)
    print("MOLECULE FETCH SUMMARY")
    print("=" * 60)

    if 'sources' in results:
        for source, result in results['sources'].items():
            status = result.get('status', 'unknown')
            status_icon = '✓' if status == 'success' else '✗'
            records = result.get('records', '-')
            print(f"  {status_icon} {source:20} {status:10} {records} records")

        success = results.get('success_count', 0)
        failed = results.get('fail_count', 0)
        print(f"\nTotal: {success} succeeded, {failed} failed")
    else:
        status = results.get('status', 'unknown')
        records = results.get('records', '-')
        source = results.get('source', 'unknown')
        print(f"  Source: {source}")
        print(f"  Status: {status}")
        print(f"  Records: {records}")

        if results.get('error'):
            print(f"  Error: {results.get('error')}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description='Fetch molecule data from external sources using data_platform services',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list                        List available sources
  %(prog)s --source chembl               Fetch ChEMBL molecules
  %(prog)s --source all                  Fetch all sources
        """
    )

    parser.add_argument(
        '--source', '-s',
        help='Molecule data source to fetch (or "all" for all sources)'
    )
    parser.add_argument(
        '--batch-size', '-b',
        type=int,
        default=100,
        help='Number of records per batch (default: 100)'
    )
    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='List available data sources'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.list:
        asyncio.run(list_sources())
        return 0

    if not args.source:
        parser.print_help()
        return 1

    logger.info(f"Started at: {datetime.now().isoformat()}")
    logger.info(f"Batch size: {args.batch_size}")

    # Fetch data
    if args.source == 'all':
        results = asyncio.run(fetch_all(batch_size=args.batch_size))
    else:
        results = asyncio.run(fetch_source(args.source, batch_size=args.batch_size))

    # Print summary
    print_summary(results)

    logger.info(f"Completed at: {datetime.now().isoformat()}")

    # Return exit code based on status
    if results.get('status') == 'failed':
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
