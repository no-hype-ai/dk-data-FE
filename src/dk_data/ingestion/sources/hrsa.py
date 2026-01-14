"""HRSA Shortage Area Data Ingestor.

Loads Health Professional Shortage Area (HPSA) data from HRSA API.
Source: https://data.hrsa.gov/api
"""

import os
import hashlib
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

import requests
from pydantic import ValidationError

from ..utils.database import get_cursor, get_connection
from ..utils.validators import HRSAShortageAreaRecord
from ..utils.retry import retry_with_backoff, RetryExhaustedError

logger = logging.getLogger(__name__)

# HRSA API endpoints
HRSA_HPSA_API_URL = os.getenv(
    'HRSA_API_URL',
    'https://data.hrsa.gov/api/hpsas'
)

# Default query parameters
DEFAULT_PARAMS = {
    'format': 'json',
    'pageSize': 1000,
}


@retry_with_backoff(max_attempts=3, initial_delay=60)
def fetch_hrsa_page(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetch a single page of HRSA data with retry logic.

    Args:
        url: API endpoint URL.
        params: Query parameters.

    Returns:
        JSON response as dictionary.
    """
    logger.debug(f"Fetching HRSA data: {url} with params {params}")

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    return response.json()


def fetch_all_hrsa_data(
    hpsa_type: str = 'Primary Care',
    state: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch all HRSA HPSA data with pagination.

    Args:
        hpsa_type: Type of HPSA (Primary Care, Mental Health, Dental).
        state: Optional state filter (2-letter abbreviation).

    Returns:
        List of all HPSA records.
    """
    all_records = []
    page = 1

    params = {**DEFAULT_PARAMS, 'hpsaType': hpsa_type}
    if state:
        params['state'] = state

    while True:
        params['page'] = page

        try:
            data = fetch_hrsa_page(HRSA_HPSA_API_URL, params)
        except RetryExhaustedError as e:
            logger.error(f"Failed to fetch HRSA data after retries: {e}")
            break
        except Exception as e:
            logger.error(f"Unexpected error fetching HRSA data: {e}")
            break

        records = data.get('results', data.get('data', []))

        if not records:
            break

        all_records.extend(records)
        logger.info(f"Fetched page {page}: {len(records)} records (total: {len(all_records)})")

        # Check if more pages
        total_pages = data.get('totalPages', 1)
        if page >= total_pages:
            break

        page += 1

    return all_records


def calculate_data_hash(data: List[Dict]) -> str:
    """Calculate hash of the data for change detection."""
    json_str = json.dumps(data, sort_keys=True, default=str)
    return hashlib.md5(json_str.encode()).hexdigest()


def load_hrsa_shortage_areas(
    hpsa_types: List[str] = None,
    states: List[str] = None,
    batch_size: int = 500
) -> dict:
    """
    Load HRSA shortage area data from API.

    Args:
        hpsa_types: List of HPSA types to fetch (default: Primary Care only).
        states: List of states to filter (default: all states).
        batch_size: Number of records to commit at once.

    Returns:
        Dictionary with ingestion statistics.
    """
    if hpsa_types is None:
        hpsa_types = ['Primary Care']

    logger.info(f"Loading HRSA shortage areas for types: {hpsa_types}")

    all_records = []
    for hpsa_type in hpsa_types:
        if states:
            for state in states:
                records = fetch_all_hrsa_data(hpsa_type=hpsa_type, state=state)
                all_records.extend(records)
        else:
            records = fetch_all_hrsa_data(hpsa_type=hpsa_type)
            all_records.extend(records)

    if not all_records:
        logger.warning("No HRSA records fetched")
        return {'status': 'empty', 'records_fetched': 0}

    logger.info(f"Total HRSA records fetched: {len(all_records)}")

    # Calculate hash for tracking
    source_hash = calculate_data_hash(all_records)

    # Check if data has changed
    with get_cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM raw.hrsa_shortage_areas
            WHERE _source_hash = %s
        """, (source_hash,))
        if cur.fetchone()[0] > 0:
            logger.info("HRSA data unchanged since last load. Skipping.")
            return {'status': 'skipped', 'reason': 'unchanged'}

    # Process records
    records_inserted = 0
    records_failed = 0
    errors = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, record_data in enumerate(all_records):
                try:
                    # Map API fields to our schema
                    record = HRSAShortageAreaRecord(
                        hpsa_id=str(record_data.get('hpsaId', record_data.get('HPSA_ID', ''))),
                        hpsa_name=record_data.get('hpsaName', record_data.get('HPSA_Name')),
                        hpsa_type=record_data.get('hpsaType', record_data.get('HPSA_Type')),
                        designation_type=record_data.get('designationType', record_data.get('Designation_Type')),
                        state_abbr=record_data.get('stateAbbreviation', record_data.get('State_Abbr', '')),
                        county_name=record_data.get('countyName', record_data.get('County_Name')),
                        hpsa_score=record_data.get('hpsaScore', record_data.get('HPSA_Score')),
                        designation_date=record_data.get('designationDate'),
                        rural_status=record_data.get('ruralStatus', record_data.get('Rural_Status'))
                    )

                    cur.execute("""
                        INSERT INTO raw.hrsa_shortage_areas (
                            hpsa_id, hpsa_name, hpsa_type, designation_type,
                            state_abbr, county_name, hpsa_score, designation_date,
                            rural_status, _source_hash
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        record.hpsa_id,
                        record.hpsa_name,
                        record.hpsa_type,
                        record.designation_type,
                        record.state_abbr,
                        record.county_name,
                        record.hpsa_score,
                        record.designation_date,
                        record.rural_status,
                        source_hash
                    ))
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()

                except ValidationError as e:
                    records_failed += 1
                    errors.append({'index': idx, 'error': str(e)})

                except Exception as e:
                    records_failed += 1
                    errors.append({'index': idx, 'error': str(e)})
                    logger.error(f"Error at record {idx}: {e}")

            conn.commit()

    logger.info(f"HRSA load complete: {records_inserted} inserted, {records_failed} failed")

    return {
        'status': 'success',
        'records_fetched': len(all_records),
        'records_inserted': records_inserted,
        'records_failed': records_failed,
        'source_hash': source_hash,
        'errors': errors[:10]
    }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Load HRSA Shortage Area Data')
    parser.add_argument('--hpsa-types', nargs='+', default=['Primary Care'],
                        help='HPSA types to fetch')
    parser.add_argument('--states', nargs='+', help='States to filter')
    parser.add_argument('--batch-size', type=int, default=500)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    result = load_hrsa_shortage_areas(
        hpsa_types=args.hpsa_types,
        states=args.states,
        batch_size=args.batch_size
    )
    print(f"Result: {result}")


if __name__ == '__main__':
    main()
