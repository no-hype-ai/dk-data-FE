#!/usr/bin/env python3
"""TAVR Data Infrastructure - Ingestion CLI.

Main entry point for data ingestion operations.
"""

import argparse
import logging
import sys
from datetime import datetime

from .sources import cms_inpatient, cms_hospital_info, cms_cost_reports, acc_tvc, hrsa
from .utils.database import init_connection_pool, close_connection_pool, get_cursor

logger = logging.getLogger(__name__)

# Available data sources
SOURCES = {
    'cms_inpatient': {
        'name': 'CMS Medicare Inpatient',
        'description': 'TAVR procedure volumes by DRG',
        'loader': cms_inpatient.load_cms_inpatient_file,
        'requires_file': True,
        'requires_fiscal_year': True,
    },
    'cms_hospital_info': {
        'name': 'CMS Hospital General Information',
        'description': 'Hospital demographics and ratings',
        'loader': cms_hospital_info.load_cms_hospital_info,
        'requires_file': True,
    },
    'cms_cost_reports': {
        'name': 'CMS Cost Reports',
        'description': 'Hospital financial metrics',
        'loader': cms_cost_reports.load_cms_cost_reports,
        'requires_file': True,
    },
    'acc_tvc': {
        'name': 'ACC TVC Certifications',
        'description': 'Transcatheter Valve Certifications',
        'loader': acc_tvc.load_acc_tvc_certifications,
        'requires_file': True,
    },
    'hrsa': {
        'name': 'HRSA Shortage Areas',
        'description': 'Health Professional Shortage Areas',
        'loader': hrsa.load_hrsa_shortage_areas,
        'requires_file': False,  # Can use API or file
        'accepts_file': True,  # File is optional
    },
}


def log_to_meta(source_name: str, result: dict) -> None:
    """Log ingestion result to meta.refresh_log."""
    try:
        with get_cursor() as cur:
            # Get source_id
            cur.execute("""
                SELECT source_id FROM meta.data_sources WHERE source_name = %s
            """, (source_name,))
            row = cur.fetchone()

            if row is None:
                logger.warning(f"Source '{source_name}' not found in meta.data_sources")
                return

            source_id = row[0]

            # Insert log entry
            status = result.get('status', 'unknown')
            cur.execute("""
                INSERT INTO meta.refresh_log (
                    source_id, refresh_started_at, refresh_completed_at,
                    status, records_fetched, records_inserted, records_updated,
                    error_message
                ) VALUES (
                    %s, %s, NOW(), %s, %s, %s, %s, %s
                )
            """, (
                source_id,
                datetime.now(),
                status,
                result.get('records_fetched', result.get('records_inserted', 0)),
                result.get('records_inserted', 0),
                result.get('records_updated', 0),
                result.get('errors', [])[:1000] if result.get('errors') else None
            ))

            # Update data_sources
            cur.execute("""
                UPDATE meta.data_sources
                SET last_refresh_attempt = NOW(),
                    last_refresh_status = %s,
                    last_successful_refresh = CASE
                        WHEN %s = 'success' THEN NOW()
                        ELSE last_successful_refresh
                    END,
                    record_count = COALESCE(%s, record_count)
                WHERE source_id = %s
            """, (
                status,
                status,
                result.get('records_inserted'),
                source_id
            ))

    except Exception as e:
        logger.error(f"Failed to log to meta: {e}")


def run_ingestion(source: str, **kwargs) -> dict:
    """Run ingestion for a specific source."""
    if source not in SOURCES:
        raise ValueError(f"Unknown source: {source}. Available: {list(SOURCES.keys())}")

    source_info = SOURCES[source]
    loader = source_info['loader']

    logger.info(f"Starting ingestion for {source_info['name']}")

    # Build kwargs for loader
    loader_kwargs = {}

    if source_info.get('requires_file'):
        if 'filepath' not in kwargs or not kwargs['filepath']:
            raise ValueError(f"Source '{source}' requires a file path")
        loader_kwargs['filepath'] = kwargs['filepath']
    elif source_info.get('accepts_file') and kwargs.get('filepath'):
        # Optional file parameter
        loader_kwargs['filepath'] = kwargs['filepath']

    if source_info.get('requires_fiscal_year'):
        if 'fiscal_year' not in kwargs or not kwargs['fiscal_year']:
            raise ValueError(f"Source '{source}' requires fiscal_year")
        loader_kwargs['fiscal_year'] = kwargs['fiscal_year']

    if 'batch_size' in kwargs:
        loader_kwargs['batch_size'] = kwargs['batch_size']

    # Run loader
    result = loader(**loader_kwargs)

    # Log to meta
    log_to_meta(source, result)

    return result


def list_sources():
    """Print available data sources."""
    print("\nAvailable Data Sources:")
    print("-" * 60)
    for key, info in SOURCES.items():
        file_req = "[file required]" if info.get('requires_file') else "[API]"
        print(f"  {key:20} - {info['description']} {file_req}")
    print()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='TAVR Data Infrastructure - Data Ingestion CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Load CMS Medicare Inpatient data
  python -m ingestion.main cms_inpatient --file data/cms_inpatient_2023.csv --fiscal-year 2023

  # Load CMS Hospital Info
  python -m ingestion.main cms_hospital_info --file data/hospital_info.csv

  # Load HRSA data from API
  python -m ingestion.main hrsa

  # List available sources
  python -m ingestion.main --list
        """
    )

    parser.add_argument('source', nargs='?', help='Data source to ingest')
    parser.add_argument('--file', '-f', dest='filepath', help='Path to data file')
    parser.add_argument('--fiscal-year', '-y', type=int, help='Fiscal year of data')
    parser.add_argument('--batch-size', '-b', type=int, default=1000, help='Batch size for commits')
    parser.add_argument('--list', '-l', action='store_true', help='List available sources')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if args.list:
        list_sources()
        return 0

    if not args.source:
        parser.print_help()
        return 1

    # Initialize connection pool
    init_connection_pool()

    try:
        result = run_ingestion(
            source=args.source,
            filepath=args.filepath,
            fiscal_year=args.fiscal_year,
            batch_size=args.batch_size
        )

        print("\nIngestion Result:")
        print("-" * 40)
        for key, value in result.items():
            if key != 'errors':
                print(f"  {key}: {value}")

        if result.get('errors'):
            print("\nFirst few errors:")
            for err in result['errors'][:5]:
                print(f"  - {err}")

        return 0 if result.get('status') in ('success', 'skipped') else 1

    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        return 1

    finally:
        close_connection_pool()


if __name__ == '__main__':
    sys.exit(main())
