#!/usr/bin/env python3
"""CLI for fetching data from external sources.

Usage:
    python -m ingestion.fetch_data --source cms_inpatient --year 2023
    python -m ingestion.fetch_data --source all
    python -m ingestion.fetch_data --list
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from dk_data.ingestion.fetchers import (
    CMSInpatientFetcher,
    CMSHospitalInfoFetcher,
    CMSCostReportsFetcher,
    ACCTVCFetcher,
    HRSAFetcher,
    PubMedFetcher,
    EMARegulatoryCIFetcher,
    OpenAlexCIFetcher,
    DrugBankFetcher,
    USPTOPatentsFetcher,
    JournalRSSFetcher,
    USPTOCIFetcher,
    HTABodiesFetcher,
    EPOOPSFetcher,
    CochraneFetcher,
    MedicalNewsFetcher,
    SECEdgarFetcher,
    UniProtFetcher,
    PDBFetcher,
    ORCIDFetcher,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


FETCHERS = {
    'cms_inpatient': {
        'class': CMSInpatientFetcher,
        'description': 'CMS Medicare Inpatient data (TAVR DRG 266/267)',
        'priority': 1,
    },
    'cms_hospital_info': {
        'class': CMSHospitalInfoFetcher,
        'description': 'CMS Hospital General Information',
        'priority': 1,
    },
    'cms_cost_reports': {
        'class': CMSCostReportsFetcher,
        'description': 'CMS Hospital Cost Reports (HCRIS)',
        'priority': 1,
    },
    'acc_tvc': {
        'class': ACCTVCFetcher,
        'description': 'ACC Transcatheter Valve Certification',
        'priority': 1,
    },
    'hrsa': {
        'class': HRSAFetcher,
        'description': 'HRSA Health Professional Shortage Areas',
        'priority': 1,
    },
    'pubmed': {
        'class': PubMedFetcher,
        'description': 'PubMed literature (NCBI E-utilities)',
        'priority': 2,
    },
    'ema_regulatory': {
        'class': EMARegulatoryCIFetcher,
        'description': 'EMA regulatory decisions (CHMP opinions, EPARs, safety signals)',
        'priority': 2,
    },
    'openalex_ci': {
        'class': OpenAlexCIFetcher,
        'description': 'OpenAlex CI pharmaceutical research works',
        'priority': 2,
    },
    'drugbank': {
        'class': DrugBankFetcher,
        'description': 'DrugBank drug data (credential-gated)',
        'priority': 3,
    },
    'uspto_patents': {
        'class': USPTOPatentsFetcher,
        'description': 'USPTO PatentsView pharma patents (credential-gated)',
        'priority': 3,
    },
    'journal_rss': {
        'class': JournalRSSFetcher,
        'description': 'Journal RSS feeds (NEJM, Lancet, JAMA, etc.)',
        'priority': 2,
    },
    'uspto_ci': {
        'class': USPTOCIFetcher,
        'description': 'USPTO PatentsView CI pharma patents',
        'priority': 2,
    },
    'hta_bodies': {
        'class': HTABodiesFetcher,
        'description': 'HTA body decisions (NICE, G-BA, HAS, PBAC)',
        'priority': 2,
    },
    'epo_ops': {
        'class': EPOOPSFetcher,
        'description': 'EPO Open Patent Services (credential-gated)',
        'priority': 3,
    },
    'cochrane': {
        'class': CochraneFetcher,
        'description': 'Cochrane Library systematic reviews',
        'priority': 3,
    },
    'medical_news': {
        'class': MedicalNewsFetcher,
        'description': 'Medical news RSS (Medscape, Healio, FiercePharma)',
        'priority': 3,
    },
    'sec_edgar': {
        'class': SECEdgarFetcher,
        'description': 'SEC EDGAR pharma filings (10-K, 10-Q, 8-K)',
        'priority': 3,
    },
    'uniprot': {
        'class': UniProtFetcher,
        'description': 'UniProt protein targets (drug target data)',
        'priority': 3,
    },
    'pdb': {
        'class': PDBFetcher,
        'description': 'RCSB PDB protein structures',
        'priority': 3,
    },
    'orcid': {
        'class': ORCIDFetcher,
        'description': 'ORCID researcher profiles (KOL identification)',
        'priority': 3,
    },
}


def list_sources():
    """Print available data sources."""
    print("\nAvailable Data Sources:")
    print("=" * 60)
    for name, info in sorted(FETCHERS.items(), key=lambda x: x[1]['priority']):
        print(f"  {name:20} - {info['description']}")
    print()


def fetch_source(source: str, year: int = None, data_dir: str = None) -> dict:
    """
    Fetch data from a single source.

    Args:
        source: Source name
        year: Optional fiscal year
        data_dir: Optional data directory

    Returns:
        Fetch result dictionary
    """
    if source not in FETCHERS:
        return {'status': 'failed', 'error': f'Unknown source: {source}'}

    fetcher_info = FETCHERS[source]
    fetcher_class = fetcher_info['class']

    logger.info(f"Initializing {source} fetcher")
    fetcher = fetcher_class(data_dir=data_dir)

    # Fetch based on source type
    if source == 'cms_inpatient':
        if year:
            result = fetcher.fetch(fiscal_year=year)
        else:
            result = fetcher.fetch_all_years()
    elif source == 'cms_cost_reports':
        if year:
            result = fetcher.fetch(fiscal_year=year)
        else:
            result = fetcher.fetch_all_years()
    else:
        result = fetcher.fetch()

    return result


def fetch_all(data_dir: str = None) -> dict:
    """
    Fetch data from all sources.

    Args:
        data_dir: Optional data directory

    Returns:
        Combined results dictionary
    """
    results = {}
    success_count = 0
    fail_count = 0

    for source in sorted(FETCHERS.keys(), key=lambda x: FETCHERS[x]['priority']):
        logger.info(f"\n{'='*60}")
        logger.info(f"Fetching: {source}")
        logger.info(f"{'='*60}")

        try:
            result = fetch_source(source, data_dir=data_dir)
            results[source] = result

            if result.get('status') == 'success':
                success_count += 1
                records = result.get('records', result.get('total_records', 'N/A'))
                logger.info(f"SUCCESS: {source} - {records} records")
            else:
                fail_count += 1
                error = result.get('error', 'Unknown error')
                logger.error(f"FAILED: {source} - {error}")

        except Exception as e:
            fail_count += 1
            results[source] = {'status': 'failed', 'error': str(e)}
            logger.exception(f"EXCEPTION: {source} - {e}")

    return {
        'status': 'success' if fail_count == 0 else 'partial',
        'sources': results,
        'success_count': success_count,
        'fail_count': fail_count,
    }


def print_summary(results: dict):
    """Print fetch summary."""
    print("\n" + "=" * 60)
    print("FETCH SUMMARY")
    print("=" * 60)

    if 'sources' in results:
        for source, result in results['sources'].items():
            status = result.get('status', 'unknown')
            status_icon = '✓' if status == 'success' else '✗'
            records = result.get('records', result.get('total_records', '-'))
            print(f"  {status_icon} {source:20} {status:10} {records} records")

        print(f"\nTotal: {results.get('success_count', 0)} succeeded, {results.get('fail_count', 0)} failed")
    else:
        status = results.get('status', 'unknown')
        records = results.get('records', results.get('total_records', '-'))
        print(f"  Status: {status}")
        print(f"  Records: {records}")

        if results.get('filepath'):
            print(f"  File: {results.get('filepath')}")

        if results.get('error'):
            print(f"  Error: {results.get('error')}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description='Fetch data from external sources for TAVR Data Platform',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list                      List available sources
  %(prog)s --source cms_inpatient      Fetch CMS Inpatient data
  %(prog)s --source cms_inpatient --year 2023
  %(prog)s --source all                Fetch all sources
        """
    )

    parser.add_argument(
        '--source', '-s',
        choices=list(FETCHERS.keys()) + ['all'],
        help='Data source to fetch'
    )
    parser.add_argument(
        '--year', '-y',
        type=int,
        help='Fiscal year (for sources that support it)'
    )
    parser.add_argument(
        '--data-dir', '-d',
        default='/tmp/data/raw',
        help='Directory to store downloaded files (default: /tmp/data/raw)'
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
        list_sources()
        return 0

    if not args.source:
        parser.print_help()
        return 1

    # Create data directory
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Data directory: {data_dir.absolute()}")
    logger.info(f"Started at: {datetime.now().isoformat()}")

    # Fetch data
    if args.source == 'all':
        results = fetch_all(data_dir=str(data_dir))
    else:
        results = fetch_source(args.source, year=args.year, data_dir=str(data_dir))

    # Print summary
    print_summary(results)

    logger.info(f"Completed at: {datetime.now().isoformat()}")

    # Return exit code based on status
    if results.get('status') == 'failed':
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
