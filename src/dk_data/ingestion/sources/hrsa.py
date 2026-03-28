"""HRSA Shortage Area Data Ingestor.

Loads Health Professional Shortage Area (HPSA) data from HRSA API.
Source: https://data.hrsa.gov/api
"""

import os
import hashlib
import logging
import json
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


def load_hrsa_from_csv(filepath: str, batch_size: int = 500) -> dict:
    """
    Load HRSA shortage area data from CSV file.

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

    # Map CSV columns to our schema (HRSA BCD_HPSA_FCT_DET CSV format)
    # Source: https://data.hrsa.gov/DataDownload/DD_Files/BCD_HPSA_FCT_DET_PC.csv
    column_mapping = {
        # HPSA ID variations
        'HPSA_ID': 'hpsa_id',
        'HPSA Source ID': 'hpsa_id',
        'HPSA ID': 'hpsa_id',
        # HPSA Name variations
        'HPSA_Name': 'hpsa_name',
        'HPSA Name': 'hpsa_name',
        # HPSA Type variations (Primary Care, Mental Health, Dental)
        'HPSA_Type': 'hpsa_type',
        'HPSA Type Description': 'hpsa_type',
        'HPSA Discipline Class': 'hpsa_type',
        # Designation Type variations
        'Designation_Type': 'designation_type',
        'HPSA Designation Type Description': 'designation_type',
        'Designation Type': 'designation_type',
        # State abbreviation variations
        'State_Abbr': 'state_abbr',
        'State Abbreviation': 'state_abbr',
        'Primary State Abbreviation': 'state_abbr',
        # County name variations
        'County_Name': 'county_name',
        'Common County Name': 'county_name',
        'County Equivalent Name': 'county_name',
        # HPSA Score variations
        'HPSA_Score': 'hpsa_score',
        'HPSA Score': 'hpsa_score',
        # Rural status variations
        'Rural_Status': 'rural_status',
        'Rural Status': 'rural_status',
        'HPSA Metropolitan Indicator Description': 'rural_status',
        'Metropolitan Indicator': 'rural_status',
        # Designation date
        'HPSA Designation Date': 'designation_date',
    }

    # Rename columns we find
    rename_map = {}
    for csv_col, db_col in column_mapping.items():
        if csv_col in df.columns:
            rename_map[csv_col] = db_col

    df = df.rename(columns=rename_map)

    # Keep only the columns we need (handles duplicate column names after rename)
    target_cols = ['hpsa_id', 'hpsa_name', 'hpsa_type', 'designation_type',
                   'state_abbr', 'county_name', 'hpsa_score', 'rural_status',
                   'designation_date']
    available_cols = [c for c in target_cols if c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()][available_cols]

    # Calculate hash
    source_hash = hashlib.md5(df.to_csv(index=False).encode()).hexdigest()[:32]

    records_inserted = 0
    records_failed = 0
    errors = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Clear existing data (full refresh)
            cur.execute("TRUNCATE TABLE hcs_raw.hrsa_shortage_areas")

            for idx, row in df.iterrows():
                try:
                    # Parse designation date if present
                    designation_date = None
                    if pd.notna(row.get('designation_date')):
                        try:
                            designation_date = pd.to_datetime(row['designation_date']).date()
                        except Exception:
                            pass

                    cur.execute("""
                        INSERT INTO hcs_raw.hrsa_shortage_areas (
                            hpsa_id, hpsa_name, hpsa_type, designation_type,
                            state_abbr, county_name, hpsa_score, designation_date,
                            rural_status, _source_hash
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        row.get('hpsa_id', ''),
                        row.get('hpsa_name', ''),
                        row.get('hpsa_type', ''),
                        row.get('designation_type', ''),
                        row.get('state_abbr', ''),
                        row.get('county_name', ''),
                        int(row['hpsa_score']) if pd.notna(row.get('hpsa_score')) else None,
                        designation_date,
                        row.get('rural_status', ''),
                        source_hash
                    ))
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()

                except Exception as e:
                    records_failed += 1
                    if len(errors) < 10:
                        errors.append({'index': idx, 'error': str(e)})

            conn.commit()

    logger.info(f"HRSA CSV load complete: {records_inserted} inserted, {records_failed} failed")

    return {
        'status': 'success',
        'records_fetched': len(df),
        'records_inserted': records_inserted,
        'records_failed': records_failed,
        'source_hash': source_hash,
        'errors': errors
    }


def load_hrsa_shortage_areas_from_records(
    records: list,
    source_hash: str = None,
    batch_size: int = 500,
) -> dict:
    """
    Load HRSA shortage area records returned by HRSAFetcher.

    The fetcher returns raw CSV DictReader rows. We map CSV column names
    (which vary across HRSA file revisions) to DB column names using the
    same column_mapping defined in load_hrsa_from_csv.

    Args:
        records: List of dicts from HRSAFetcher.fetch().
        source_hash: Hash from the fetcher for idempotency.
        batch_size: Commit interval.

    Returns:
        Dictionary with ingestion statistics.
    """
    logger.info(f"Loading {len(records)} HRSA shortage area records from fetcher")

    if not records:
        return {'status': 'skipped', 'reason': 'no_records'}

    # Build lookup: CSV column name (any case variation) -> DB column name.
    # Multiple CSV columns can map to the same DB column; first match wins per row.
    col_map = {
        'HPSA_ID': 'hpsa_id', 'HPSA Source ID': 'hpsa_id', 'HPSA ID': 'hpsa_id',
        'HPSA_Name': 'hpsa_name', 'HPSA Name': 'hpsa_name',
        'HPSA_Type': 'hpsa_type', 'HPSA Type Description': 'hpsa_type',
        'HPSA Discipline Class': 'hpsa_type',
        'Designation_Type': 'designation_type',
        'HPSA Designation Type Description': 'designation_type',
        'Designation Type': 'designation_type',
        'State_Abbr': 'state_abbr', 'State Abbreviation': 'state_abbr',
        'Primary State Abbreviation': 'state_abbr',
        'County_Name': 'county_name', 'Common County Name': 'county_name',
        'County Equivalent Name': 'county_name',
        'HPSA_Score': 'hpsa_score', 'HPSA Score': 'hpsa_score',
        'Rural_Status': 'rural_status', 'Rural Status': 'rural_status',
        'HPSA Metropolitan Indicator Description': 'rural_status',
        'Metropolitan Indicator': 'rural_status',
        'HPSA Designation Date': 'designation_date',
    }

    records_inserted = 0
    records_failed = 0
    errors = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw in enumerate(records):
                try:
                    # Map raw CSV keys to DB column names (first match wins)
                    row: dict = {}
                    for csv_col, val in raw.items():
                        db_col = col_map.get(csv_col)
                        if db_col and db_col not in row:
                            row[db_col] = val if val else None

                    # Parse designation_date
                    designation_date = None
                    if row.get('designation_date'):
                        try:
                            import pandas as _pd
                            designation_date = _pd.to_datetime(row['designation_date']).date()
                        except Exception:
                            pass

                    # Parse hpsa_score
                    hpsa_score = None
                    if row.get('hpsa_score'):
                        try:
                            hpsa_score = int(float(row['hpsa_score']))
                        except (TypeError, ValueError):
                            pass

                    cur.execute("""
                        INSERT INTO hcs_raw.hrsa_shortage_areas (
                            hpsa_id, hpsa_name, hpsa_type, designation_type,
                            state_abbr, county_name, hpsa_score, designation_date,
                            rural_status, _source_hash
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        row.get('hpsa_id', ''),
                        row.get('hpsa_name', ''),
                        row.get('hpsa_type', ''),
                        row.get('designation_type', ''),
                        row.get('state_abbr', ''),
                        row.get('county_name', ''),
                        hpsa_score,
                        designation_date,
                        row.get('rural_status', ''),
                        source_hash,
                    ))
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()

                except Exception as e:
                    records_failed += 1
                    if len(errors) < 10:
                        errors.append({'index': idx, 'error': str(e)})

            conn.commit()

    logger.info(f"HRSA records-based load complete: {records_inserted} inserted, {records_failed} failed")
    return {
        'status': 'success',
        'records_inserted': records_inserted,
        'records_failed': records_failed,
        'source_hash': source_hash,
        'errors': errors,
    }


def load_hrsa_shortage_areas(
    filepath: str = None,
    hpsa_types: List[str] = None,
    states: List[str] = None,
    batch_size: int = 500
) -> dict:
    """
    Load HRSA shortage area data from CSV file or API.

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

    # Download the HRSA bulk CSV and load from it.
    # The HRSA JSON API (https://data.hrsa.gov/api/hpsas) returns HTML and is unavailable.
    # Use the official HRSA Data Download bulk CSV instead.
    import tempfile
    _BULK_URL = "https://data.hrsa.gov/DataDownload/DD_Files/BCD_HPSA_FCT_DET_PC.csv"
    logger.info("Downloading HRSA bulk CSV from %s", _BULK_URL)
    try:
        resp = requests.get(_BULK_URL, timeout=300, stream=True)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".csv", delete=False, prefix="hrsa_hpsa_"
        ) as tmp:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                tmp.write(chunk)
            tmp_path = tmp.name
        logger.info("Downloaded HRSA bulk CSV to %s", tmp_path)
        return load_hrsa_from_csv(tmp_path, batch_size)
    except Exception as e:
        logger.error("Failed to download HRSA bulk CSV from %s: %s", _BULK_URL, e)
        return {'status': 'failed', 'error': f"Bulk CSV download failed: {e}"}

    logger.info(f"Total HRSA records fetched: {len(all_records)}")

    # Calculate hash for tracking
    source_hash = calculate_data_hash(all_records)

    # Check if data has changed
    with get_cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM hcs_raw.hrsa_shortage_areas
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
                        INSERT INTO hcs_raw.hrsa_shortage_areas (
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
