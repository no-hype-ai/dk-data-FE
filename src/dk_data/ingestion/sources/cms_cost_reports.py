"""CMS Cost Reports Ingestor.

Loads hospital financial metrics from CMS Cost Reports (HCRIS).
Source: https://data.cms.gov/provider-compliance/cost-report
"""

import hashlib
import logging
from pathlib import Path
from decimal import Decimal
from typing import Optional

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, get_connection
from ..utils.validators import CMSCostReportRecord

logger = logging.getLogger(__name__)

# Column mapping for cost report data - supports multiple column name formats
# HCRIS raw files (RPT file): PRVDR_NUM, FY_BGN_DT, FY_END_DT
# data.cms.gov Hospital Provider Cost Report API: Provider CCN, Fiscal Year Begin Date, etc.
COLUMN_MAPPING = {
    # Provider ID — HCRIS raw format
    'PRVDR_NUM': 'provider_id',
    # Provider ID — data.cms.gov API / processed format
    'Provider CCN': 'provider_id',
    'Provider Number': 'provider_id',
    # Fiscal year dates — HCRIS raw format
    'FY_BGN_DT': 'fiscal_year_begin',
    'FY_END_DT': 'fiscal_year_end',
    # Fiscal year dates — data.cms.gov API / processed format
    'Fiscal Year Begin Date': 'fiscal_year_begin',
    'Fiscal Year End Date': 'fiscal_year_end',
    # Bed count variations
    'Total Beds': 'total_beds',
    'Number of Beds': 'total_beds',
    # Discharge count variations
    'Total Discharges': 'total_discharges',
    'Total Discharges (V + XVIII + XIX + Unknown)': 'total_discharges',
    # Revenue variations
    'Net Patient Revenue': 'net_patient_revenue',
    # Operating expenses variations
    'Total Operating Expenses': 'total_operating_expenses',
    'Less Total Operating Expense': 'total_operating_expenses',
}


def calculate_file_hash(filepath: str) -> str:
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def calculate_operating_margin(revenue: Optional[Decimal], expenses: Optional[Decimal]) -> Optional[Decimal]:
    """Calculate operating margin as (revenue - expenses) / revenue."""
    if revenue is None or expenses is None or revenue == 0:
        return None
    try:
        margin = (revenue - expenses) / revenue
        return round(margin, 4)
    except (ZeroDivisionError, TypeError):
        return None


def load_cms_cost_reports(
    filepath: str,
    batch_size: int = 1000
) -> dict:
    """
    Load CMS Cost Report data from CSV file.

    Args:
        filepath: Path to the CMS CSV file.
        batch_size: Number of records to commit at once.

    Returns:
        Dictionary with ingestion statistics.
    """
    logger.info(f"Loading CMS Cost Reports from {filepath}")

    source_hash = calculate_file_hash(filepath)
    source_file = Path(filepath).name

    # Check if already loaded
    with get_cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM hcs_raw.cms_cost_reports
            WHERE _source_hash = %s
        """, (source_hash,))
        if cur.fetchone()[0] > 0:
            logger.warning(f"File {source_file} already loaded. Skipping.")
            return {'status': 'skipped', 'reason': 'already_loaded'}

    # Read CSV — provider number columns must be read as TEXT to preserve
    # leading zeros (e.g., "010001"). Date parsing is deferred to avoid
    # parse_dates errors when HCRIS raw files use FY_BGN_DT / FY_END_DT
    # column names instead of the API column names.
    df = pd.read_csv(
        filepath,
        dtype={
            # HCRIS raw RPT file format
            'PRVDR_NUM': str,
            # data.cms.gov API / processed format
            'Provider CCN': str,
            'Provider Number': str,
        },
        low_memory=False
    )

    # Normalize date columns after rename (handles both name formats)
    df = df.rename(columns=COLUMN_MAPPING)

    for date_col in ('fiscal_year_begin', 'fiscal_year_end'):
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce').dt.date

    logger.info(f"Found {len(df)} cost report records")

    # Process records
    records_inserted = 0
    records_failed = 0
    errors = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in df.iterrows():
                try:
                    # Calculate operating margin
                    net_revenue = row.get('net_patient_revenue')
                    total_expenses = row.get('total_operating_expenses')

                    if pd.notna(net_revenue):
                        net_revenue = Decimal(str(net_revenue))
                    else:
                        net_revenue = None

                    if pd.notna(total_expenses):
                        total_expenses = Decimal(str(total_expenses))
                    else:
                        total_expenses = None

                    operating_margin = calculate_operating_margin(net_revenue, total_expenses)

                    # Validate record
                    record = CMSCostReportRecord(
                        provider_id=row['provider_id'],
                        fiscal_year_begin=row.get('fiscal_year_begin'),
                        fiscal_year_end=row.get('fiscal_year_end'),
                        total_beds=int(row['total_beds']) if pd.notna(row.get('total_beds')) else None,
                        total_discharges=int(row['total_discharges']) if pd.notna(row.get('total_discharges')) else None,
                        net_patient_revenue=net_revenue,
                        total_operating_expenses=total_expenses,
                        operating_margin=operating_margin
                    )

                    cur.execute("""
                        INSERT INTO hcs_raw.cms_cost_reports (
                            provider_id, fiscal_year_begin, fiscal_year_end,
                            total_beds, total_discharges, net_patient_revenue,
                            total_operating_expenses, operating_margin, _source_hash
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        record.provider_id,
                        record.fiscal_year_begin,
                        record.fiscal_year_end,
                        record.total_beds,
                        record.total_discharges,
                        record.net_patient_revenue,
                        record.total_operating_expenses,
                        record.operating_margin,
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

    logger.info(f"CMS Cost Reports load complete: {records_inserted} inserted, {records_failed} failed")

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

    parser = argparse.ArgumentParser(description='Load CMS Cost Reports')
    parser.add_argument('filepath', help='Path to CMS CSV file')
    parser.add_argument('--batch-size', type=int, default=1000)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    result = load_cms_cost_reports(args.filepath, args.batch_size)
    print(f"Result: {result}")


if __name__ == '__main__':
    main()
