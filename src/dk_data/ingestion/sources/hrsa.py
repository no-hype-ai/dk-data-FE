"""HRSA Shortage Area Data Ingestor.

Loads Health Professional Shortage Area (HPSA) data from HRSA API or CSV.
Source: https://data.hrsa.gov/api

Stores full raw response as JSONB.
"""

import os
import hashlib
import logging
import json
from typing import Optional, Dict, Any, List

import requests

from ..utils.database import get_cursor, get_connection
from ..utils.retry import retry_with_backoff, RetryExhaustedError

logger = logging.getLogger(__name__)

SOURCE_NAME = 'hrsa'
TABLE = 'mol_raw.hrsa_shortage_areas'
API_ENDPOINT = 'hrsa_hpsa'

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


def load_hrsa_from_csv(filepath: str, batch_size: int = 500) -> dict:
    """
    Load HRSA shortage area data from CSV file. Stores full raw response as JSONB.

    Args:
        filepath: Path to HRSA CSV file.
        batch_size: Number of records to commit at once.

    Returns:
        Dictionary with ingestion statistics.
    """
    import pandas as pd

    logger.info(f"Loading HRSA shortage areas from CSV: {filepath}")

    try:
        df = pd.read_csv(filepath, dtype=str, low_memory=False)
        logger.info(f"Loaded {len(df)} records from CSV")
    except Exception as e:
        logger.error(f"Failed to read CSV: {e}")
        return {'status': 'failed', 'error': str(e)}

    inserted = 0
    failed = 0
    errors = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Clear existing data (full refresh)
            cur.execute(f"TRUNCATE TABLE {TABLE}")

            for idx, row in df.iterrows():
                try:
                    raw_record = row.to_dict()
                    response_body = json.dumps(raw_record, default=str)
                    response_hash = hashlib.sha256(response_body.encode()).hexdigest()
                    request_id = raw_record.get('HPSA_ID',
                                    raw_record.get('HPSA Source ID',
                                    raw_record.get('HPSA ID',
                                    f'hrsa_{idx}')))

                    cur.execute(f"""
                        INSERT INTO {TABLE} (
                            request_id, api_endpoint,
                            response_status, response_body, response_body_hash,
                            source_id
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (response_body_hash)
                        WHERE response_body_hash IS NOT NULL
                        DO NOTHING
                    """, (
                        str(request_id), 'hrsa_csv',
                        200, response_body, response_hash,
                        SOURCE_NAME,
                    ))
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()
                except Exception as e:
                    failed += 1
                    if len(errors) < 10:
                        errors.append({'index': idx, 'error': str(e)[:200]})
                    logger.error(f"{SOURCE_NAME} CSV record {idx} failed: {e}")

            conn.commit()

    logger.info(f"{SOURCE_NAME} CSV load: {inserted} inserted, {failed} failed")

    return {
        'status': 'success' if failed == 0 else 'partial',
        'records_fetched': len(df),
        'records_inserted': inserted,
        'records_failed': failed,
        'errors': errors[:10],
    }


def load_hrsa_shortage_areas(
    filepath: str = None,
    hpsa_types: List[str] = None,
    states: List[str] = None,
    batch_size: int = 500
) -> dict:
    """
    Load HRSA shortage area data from CSV file or API. Stores full raw response as JSONB.

    Args:
        filepath: Path to CSV file (if provided, loads from file).
        hpsa_types: List of HPSA types to fetch (default: Primary Care only).
        states: List of states to filter (default: all states).
        batch_size: Number of records to commit at once.

    Returns:
        Dictionary with ingestion statistics.
    """
    # If filepath provided, load from CSV
    if filepath:
        return load_hrsa_from_csv(filepath, batch_size)

    # Otherwise try API
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

    # Process records
    inserted = 0
    failed = 0
    errors = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(all_records):
                try:
                    response_body = json.dumps(raw_record, default=str)
                    response_hash = hashlib.sha256(response_body.encode()).hexdigest()
                    request_id = raw_record.get('hpsaId',
                                    raw_record.get('HPSA_ID',
                                    f'hrsa_{idx}'))

                    cur.execute(f"""
                        INSERT INTO {TABLE} (
                            request_id, api_endpoint,
                            response_status, response_body, response_body_hash,
                            source_id
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (response_body_hash)
                        WHERE response_body_hash IS NOT NULL
                        DO NOTHING
                    """, (
                        str(request_id), API_ENDPOINT,
                        200, response_body, response_hash,
                        SOURCE_NAME,
                    ))
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()
                except Exception as e:
                    failed += 1
                    if len(errors) < 10:
                        errors.append({'index': idx, 'error': str(e)[:200]})
                    logger.error(f"{SOURCE_NAME} API record {idx} failed: {e}")

            conn.commit()

    logger.info(f"{SOURCE_NAME} API load: {inserted} inserted, {failed} failed")

    return {
        'status': 'success' if failed == 0 else 'partial',
        'records_fetched': len(all_records),
        'records_inserted': inserted,
        'records_failed': failed,
        'source_hash': source_hash,
        'errors': errors[:10],
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
