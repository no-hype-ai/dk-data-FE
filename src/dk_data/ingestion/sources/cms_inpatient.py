"""CMS Medicare Inpatient Data Ingestor.

Loads TAVR procedure volumes (DRG 266/267) from CMS Medicare Inpatient files.
Source: https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals
"""

import hashlib
import logging
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, get_connection
from ..utils.validators import CMSMedicareInpatientRecord, TAVR_DRG_CODES

logger = logging.getLogger(__name__)

# CMS column mapping (from CMS file headers to our schema)
COLUMN_MAPPING = {
    'Rndrng_Prvdr_CCN': 'provider_id',
    'Rndrng_Prvdr_Org_Name': 'provider_name',
    'Rndrng_Prvdr_St': 'provider_street_address',
    'Rndrng_Prvdr_City': 'provider_city',
    'Rndrng_Prvdr_State_Abrvtn': 'provider_state',
    'Rndrng_Prvdr_Zip5': 'provider_zip_code',
    'DRG_Cd': 'drg_code',
    'DRG_Desc': 'drg_description',
    'Tot_Dschrgs': 'total_discharges',
    'Avg_Submtd_Cvrd_Chrg': 'average_covered_charges',
    'Avg_Tot_Pymt_Amt': 'average_total_payments',
    'Avg_Mdcr_Pymt_Amt': 'average_medicare_payments',
}


def calculate_file_hash(filepath: str) -> str:
    """Calculate MD5 hash of a file for deduplication."""
    hash_md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def load_cms_inpatient_file(
    filepath: str,
    fiscal_year: int,
    batch_size: int = 1000
) -> dict:
    """
    Load CMS Medicare Inpatient data from CSV file.

    Args:
        filepath: Path to the CMS CSV file.
        fiscal_year: Fiscal year of the data.
        batch_size: Number of records to commit at once.

    Returns:
        Dictionary with ingestion statistics.
    """
    logger.info(f"Loading CMS Medicare Inpatient data from {filepath} (FY{fiscal_year})")

    # Calculate file hash for tracking
    source_hash = calculate_file_hash(filepath)
    source_file = Path(filepath).name

    # Check if file was already loaded
    with get_cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM hcs_raw.cms_medicare_inpatient
            WHERE _source_hash = %s
        """, (source_hash,))
        existing_count = cur.fetchone()[0]

        if existing_count > 0:
            logger.warning(f"File {source_file} already loaded ({existing_count} records). Skipping.")
            return {
                'status': 'skipped',
                'reason': 'already_loaded',
                'existing_records': existing_count
            }

    # Read CSV file - handle both CMS format and direct column names
    df = pd.read_csv(
        filepath,
        dtype={
            'Rndrng_Prvdr_CCN': str,
            'DRG_Cd': str,
            'Rndrng_Prvdr_Zip5': str,
            'provider_id': str,
            'drg_code': str,
            'provider_zip_code': str,
        },
        low_memory=False
    )

    # Rename columns
    df = df.rename(columns=COLUMN_MAPPING)

    # Filter for TAVR DRG codes only
    df = df[df['drg_code'].isin(TAVR_DRG_CODES)]
    logger.info(f"Found {len(df)} TAVR records (DRG 266/267)")

    if df.empty:
        return {
            'status': 'empty',
            'reason': 'no_tavr_records',
            'total_records': 0
        }

    # Add metadata columns
    df['fiscal_year'] = fiscal_year
    df['_source_file'] = source_file
    df['_source_hash'] = source_hash

    # Validate and insert records
    records_inserted = 0
    records_failed = 0
    errors = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in df.iterrows():
                try:
                    # Validate record
                    record = CMSMedicareInpatientRecord(
                        provider_id=row['provider_id'],
                        provider_name=row.get('provider_name'),
                        provider_street_address=row.get('provider_street_address'),
                        provider_city=row.get('provider_city'),
                        provider_state=row.get('provider_state'),
                        provider_zip_code=row.get('provider_zip_code'),
                        drg_code=row['drg_code'],
                        drg_description=row.get('drg_description'),
                        total_discharges=int(row['total_discharges']),
                        average_covered_charges=row.get('average_covered_charges'),
                        average_total_payments=row.get('average_total_payments'),
                        average_medicare_payments=row.get('average_medicare_payments'),
                        fiscal_year=fiscal_year
                    )

                    # Insert record
                    cur.execute("""
                        INSERT INTO hcs_raw.cms_medicare_inpatient (
                            provider_id, provider_name, provider_street_address,
                            provider_city, provider_state, provider_zip_code,
                            drg_code, drg_description, total_discharges,
                            average_covered_charges, average_total_payments,
                            average_medicare_payments, fiscal_year,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (provider_id, fiscal_year, drg_code)
                        DO UPDATE SET
                            provider_name = EXCLUDED.provider_name,
                            total_discharges = EXCLUDED.total_discharges,
                            average_covered_charges = EXCLUDED.average_covered_charges,
                            average_total_payments = EXCLUDED.average_total_payments,
                            average_medicare_payments = EXCLUDED.average_medicare_payments,
                            _loaded_at = NOW(),
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash
                    """, (
                        record.provider_id,
                        record.provider_name,
                        record.provider_street_address,
                        record.provider_city,
                        record.provider_state,
                        record.provider_zip_code,
                        record.drg_code,
                        record.drg_description,
                        record.total_discharges,
                        record.average_covered_charges,
                        record.average_total_payments,
                        record.average_medicare_payments,
                        record.fiscal_year,
                        source_file,
                        source_hash
                    ))
                    records_inserted += 1

                    # Commit in batches
                    if records_inserted % batch_size == 0:
                        conn.commit()
                        logger.debug(f"Committed {records_inserted} records")

                except ValidationError as e:
                    records_failed += 1
                    errors.append({'row': idx, 'error': str(e)})
                    if records_failed <= 10:
                        logger.warning(f"Validation error at row {idx}: {e}")

                except Exception as e:
                    records_failed += 1
                    errors.append({'row': idx, 'error': str(e)})
                    logger.error(f"Error at row {idx}: {e}")

            # Final commit
            conn.commit()

    logger.info(f"CMS Inpatient load complete: {records_inserted} inserted, {records_failed} failed")

    return {
        'status': 'success',
        'records_inserted': records_inserted,
        'records_failed': records_failed,
        'source_file': source_file,
        'source_hash': source_hash,
        'errors': errors[:10] if errors else []
    }


def update_data_source_metadata(source_id: int, result: dict) -> None:
    """Update meta.data_sources with refresh results."""
    with get_cursor() as cur:
        status = 'success' if result.get('status') == 'success' else 'failed'
        cur.execute("""
            UPDATE meta.data_sources
            SET last_refresh_attempt = NOW(),
                last_refresh_status = %s,
                last_successful_refresh = CASE WHEN %s = 'success' THEN NOW() ELSE last_successful_refresh END,
                record_count = COALESCE(%s, record_count)
            WHERE source_id = %s
        """, (status, status, result.get('records_inserted'), source_id))


def main():
    """CLI entry point for CMS Inpatient ingestion."""
    import argparse

    parser = argparse.ArgumentParser(description='Load CMS Medicare Inpatient data')
    parser.add_argument('filepath', help='Path to CMS CSV file')
    parser.add_argument('--fiscal-year', type=int, required=True, help='Fiscal year of data')
    parser.add_argument('--batch-size', type=int, default=1000, help='Batch size for commits')

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    result = load_cms_inpatient_file(
        filepath=args.filepath,
        fiscal_year=args.fiscal_year,
        batch_size=args.batch_size
    )

    print(f"Result: {result}")


if __name__ == '__main__':
    main()
