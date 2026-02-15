"""ACC TVC Certification Data Ingestor.

Loads Transcatheter Valve Certification data from NCDR Public Reporting
CSV files into the ``raw.acc_tvc_certification`` table.

Supports two CSV formats:
  1. NCDR TVTMetrics / merged CSV  (columns: FacilityBrandedName, State, ...)
  2. Legacy / manual upload CSV     (columns: Facility Name, City, ...)
"""

import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, get_connection
from ..utils.validators import ACCTVCCertificationRecord

logger = logging.getLogger(__name__)

# Column mapping for NCDR TVTMetrics / Hospitals merged CSV
NCDR_COLUMN_MAPPING = {
    'FacilityBrandedName': 'facility_name',
    'Address': 'facility_address',
    'City': 'city',
    'State': 'state',
    'StateCode': 'state',
    'Zip': 'zip_code',
    'TranscatheterValveCertification': 'certification_type',
    'CumulativeTAVRvolume': 'cumulative_tavr_volume',
    'AnnualTAVRVolume': 'annual_tavr_volume',
    'ParticipantRating': 'participant_rating',
    'FacilityLinkingID': 'facility_linking_id',
    'MPN': 'mpn',
    'AHA': 'aha_id',
    'NPI': 'npi',
    'EnrollmentDate': 'enrollment_date',
}

# Column mapping for legacy / manual-upload CSV
LEGACY_COLUMN_MAPPING = {
    'Facility Name': 'facility_name',
    'Address': 'facility_address',
    'City': 'city',
    'State': 'state',
    'Zip': 'zip_code',
    'ZIP': 'zip_code',
    'Zip Code': 'zip_code',
    'Certification Type': 'certification_type',
    'Certification Date': 'certification_date',
    'Expiration Date': 'expiration_date',
}


def calculate_file_hash(filepath: str) -> str:
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def parse_date(value) -> Optional[datetime]:
    """Parse various date formats."""
    if pd.isna(value):
        return None

    if isinstance(value, (datetime, pd.Timestamp)):
        return value.date() if hasattr(value, 'date') else value

    date_formats = ['%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%Y/%m/%d']

    for fmt in date_formats:
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue

    logger.warning(f"Could not parse date: {value}")
    return None


def _detect_format(columns: list[str]) -> str:
    """Detect whether the CSV is NCDR format or legacy format.

    Returns:
        'ncdr' or 'legacy'
    """
    ncdr_indicators = {'FacilityBrandedName', 'FacilityLinkingID', 'RegistryName'}
    if ncdr_indicators & set(columns):
        return 'ncdr'
    return 'legacy'


def _apply_column_mapping(df: pd.DataFrame, fmt: str) -> pd.DataFrame:
    """Rename columns based on detected format."""
    mapping = NCDR_COLUMN_MAPPING if fmt == 'ncdr' else LEGACY_COLUMN_MAPPING

    rename_map = {}
    for orig_col in df.columns:
        for map_key, map_val in mapping.items():
            if orig_col.strip() == map_key:
                rename_map[orig_col] = map_val
                break

    return df.rename(columns=rename_map)


def load_acc_tvc_certifications(
    filepath: str,
    batch_size: int = 500
) -> dict:
    """Load ACC TVC Certification data from CSV file.

    Handles both NCDR PublicReportingApi CSVs and legacy manual-upload
    CSVs via automatic column-format detection.

    Args:
        filepath: Path to the ACC TVC CSV file.
        batch_size: Number of records to commit at once.

    Returns:
        Dictionary with ingestion statistics.
    """
    logger.info(f"Loading ACC TVC Certifications from {filepath}")

    source_hash = calculate_file_hash(filepath)
    source_file = Path(filepath).name

    # Check if already loaded
    with get_cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM raw.acc_tvc_certification
            WHERE _source_hash = %s
        """, (source_hash,))
        if cur.fetchone()[0] > 0:
            logger.warning(f"File {source_file} already loaded. Skipping.")
            return {'status': 'skipped', 'reason': 'already_loaded'}

    # Read CSV with flexible column detection
    df = pd.read_csv(
        filepath,
        dtype=str,
        low_memory=False
    )

    # Normalize column names
    df.columns = df.columns.str.strip()

    # Auto-detect format and apply mapping
    fmt = _detect_format(list(df.columns))
    logger.info(f"Detected CSV format: {fmt}")
    df = _apply_column_mapping(df, fmt)

    logger.info(f"Found {len(df)} certification records")

    # Process records
    records_inserted = 0
    records_failed = 0
    errors = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in df.iterrows():
                try:
                    # Determine certification type
                    cert_type = row.get('certification_type', 'Transcatheter Valve Certification')
                    if pd.isna(cert_type) or not str(cert_type).strip():
                        cert_type = 'Transcatheter Valve Certification'

                    # Validate record
                    record = ACCTVCCertificationRecord(
                        facility_name=row['facility_name'],
                        facility_address=row.get('facility_address'),
                        city=row.get('city'),
                        state=row.get('state'),
                        zip_code=row.get('zip_code'),
                        certification_type=str(cert_type).strip(),
                        certification_date=parse_date(row.get('certification_date')),
                        expiration_date=parse_date(row.get('expiration_date'))
                    )

                    cur.execute("""
                        INSERT INTO raw.acc_tvc_certification (
                            facility_name, facility_address, city, state,
                            zip_code, certification_type, certification_date,
                            expiration_date, _source_file, _source_hash
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        record.facility_name,
                        record.facility_address,
                        record.city,
                        record.state,
                        record.zip_code,
                        record.certification_type,
                        record.certification_date,
                        record.expiration_date,
                        source_file,
                        source_hash
                    ))
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()

                except ValidationError as e:
                    records_failed += 1
                    errors.append({'row': idx, 'error': str(e)})
                    if records_failed <= 5:
                        logger.warning(f"Validation error at row {idx}: {e}")

                except Exception as e:
                    records_failed += 1
                    errors.append({'row': idx, 'error': str(e)})
                    logger.error(f"Error at row {idx}: {e}")

            conn.commit()

    logger.info(f"ACC TVC load complete: {records_inserted} inserted, {records_failed} failed")

    return {
        'status': 'success',
        'records_inserted': records_inserted,
        'records_failed': records_failed,
        'source_file': source_file,
        'errors': errors[:10]
    }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Load ACC TVC Certifications')
    parser.add_argument('filepath', help='Path to ACC TVC CSV file')
    parser.add_argument('--batch-size', type=int, default=500)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    result = load_acc_tvc_certifications(args.filepath, args.batch_size)
    print(f"Result: {result}")


if __name__ == '__main__':
    main()
