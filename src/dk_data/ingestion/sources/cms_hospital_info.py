"""CMS Hospital General Information Ingestor.

Loads hospital demographics, ownership, and quality ratings from CMS.
Source: https://data.cms.gov/provider-data/dataset/xubh-q36u
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, get_connection
from ..utils.validators import CMSHospitalInfoRecord

logger = logging.getLogger(__name__)

# CMS column mapping - supports multiple column name formats
# CMS provider-data portal uses underscore-separated names (e.g., Facility_ID)
# Older exports may use space-separated names (e.g., Facility ID)
COLUMN_MAPPING = {
    # Provider ID variations
    'Facility_ID': 'provider_id',
    'Facility ID': 'provider_id',
    # Hospital name variations
    'Facility_Name': 'hospital_name',
    'Facility Name': 'hospital_name',
    # Address variations
    'Address': 'address',
    # City variations
    'City_Town': 'city',
    'City/Town': 'city',
    'City': 'city',
    # State variations
    'State': 'state',
    # ZIP Code variations
    'ZIP_Code': 'zip_code',
    'ZIP Code': 'zip_code',
    # County variations
    'County_Parish': 'county_name',
    'County/Parish': 'county_name',
    'County Name': 'county_name',
    # Phone variations
    'Phone_Number': 'phone_number',
    'Phone Number': 'phone_number',
    'Telephone Number': 'phone_number',
    # Hospital Type variations
    'Hospital_Type': 'hospital_type',
    'Hospital Type': 'hospital_type',
    # Ownership variations
    'Hospital_Ownership': 'hospital_ownership',
    'Hospital Ownership': 'hospital_ownership',
    # Emergency Services variations
    'Emergency_Services': 'emergency_services',
    'Emergency Services': 'emergency_services',
    # Rating variations
    'Hospital_overall_rating': 'hospital_overall_rating',
    'Hospital overall rating': 'hospital_overall_rating',
}


def calculate_file_hash(filepath: str) -> str:
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def parse_emergency_services(value) -> Optional[bool]:
    """Parse emergency services field to boolean."""
    if pd.isna(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('yes', 'true', '1', 'y')
    return bool(value)


def parse_rating(value) -> Optional[int]:
    """Parse hospital rating to integer."""
    if pd.isna(value):
        return None
    if value == 'Not Available':
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def load_cms_hospital_info(
    filepath: str,
    batch_size: int = 1000
) -> dict:
    """
    Load CMS Hospital General Information from CSV file.

    Args:
        filepath: Path to the CMS CSV file.
        batch_size: Number of records to commit at once.

    Returns:
        Dictionary with ingestion statistics.
    """
    logger.info(f"Loading CMS Hospital Info from {filepath}")

    source_hash = calculate_file_hash(filepath)
    source_file = Path(filepath).name

    # Check if already loaded
    with get_cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM hcs_raw.cms_hospital_info
            WHERE _source_hash = %s
        """, (source_hash,))
        if cur.fetchone()[0] > 0:
            logger.warning(f"File {source_file} already loaded. Skipping.")
            return {'status': 'skipped', 'reason': 'already_loaded'}

    # Read CSV - handle both CMS underscore format (Facility_ID) and
    # legacy space format (Facility ID) by specifying dtype for both variants
    df = pd.read_csv(
        filepath,
        dtype={
            # Underscore format (current CMS provider-data portal)
            'Facility_ID': str,
            'ZIP_Code': str,
            'Phone_Number': str,
            # Space format (older exports)
            'Facility ID': str,
            'ZIP Code': str,
            'Phone Number': str,
            # Post-rename names (in case file was pre-normalized)
            'provider_id': str,
            'zip_code': str,
            'phone_number': str,
        },
        low_memory=False
    )

    # Rename columns
    df = apply_column_mapping(df, COLUMN_MAPPING)

    logger.info(f"Found {len(df)} hospital records")

    # Process records
    records_inserted = 0
    records_failed = 0
    errors = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in df.iterrows():
                try:
                    # Validate record
                    record = CMSHospitalInfoRecord(
                        provider_id=row['provider_id'],
                        hospital_name=row['hospital_name'],
                        address=row.get('address'),
                        city=row.get('city'),
                        state=row['state'],
                        zip_code=row.get('zip_code'),
                        county_name=row.get('county_name'),
                        phone_number=row.get('phone_number'),
                        hospital_type=row.get('hospital_type'),
                        hospital_ownership=row.get('hospital_ownership'),
                        emergency_services=parse_emergency_services(row.get('emergency_services')),
                        hospital_overall_rating=parse_rating(row.get('hospital_overall_rating'))
                    )

                    cur.execute("""
                        INSERT INTO hcs_raw.cms_hospital_info (
                            provider_id, hospital_name, address, city, state,
                            zip_code, county_name, phone_number, hospital_type,
                            hospital_ownership, emergency_services, hospital_overall_rating,
                            _source_hash
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        record.provider_id,
                        record.hospital_name,
                        record.address,
                        record.city,
                        record.state,
                        record.zip_code,
                        record.county_name,
                        record.phone_number,
                        record.hospital_type,
                        record.hospital_ownership,
                        record.emergency_services,
                        record.hospital_overall_rating,
                        source_hash
                    ))
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()

                except ValidationError as e:
                    records_failed += 1
                    errors.append({'row': idx, 'error': str(e)})

                except Exception as e:
                    records_failed += 1
                    errors.append({'row': idx, 'error': str(e)})
                    logger.error(f"Error at row {idx}: {e}")

            conn.commit()

    logger.info(f"CMS Hospital Info load complete: {records_inserted} inserted, {records_failed} failed")

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

    parser = argparse.ArgumentParser(description='Load CMS Hospital General Information')
    parser.add_argument('filepath', help='Path to CMS CSV file')
    parser.add_argument('--batch-size', type=int, default=1000)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    result = load_cms_hospital_info(args.filepath, args.batch_size)
    print(f"Result: {result}")


if __name__ == '__main__':
    main()
