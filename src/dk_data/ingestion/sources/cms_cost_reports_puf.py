"""CMS Cost Reports PUF loader. Loads to hcs_raw.cms_cost_reports_puf.

NOTE: This is distinct from the existing cms_cost_reports.py which targets hcs_raw.cms_cost_reports.
This loader targets hcs_raw.cms_cost_reports_puf as part of the PUF ingestion pipeline.
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSCostReportsPUFRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Provider ID': 'provider_id',
    'Provider CCN': 'provider_id',
    'Hospital Name': 'hospital_name',
    'City': 'city',
    'State': 'state',
    'Zip Code': 'zip_code',
    'Fiscal Year Begin': 'fiscal_year_begin',
    'Fiscal Year End': 'fiscal_year_end',
    'Number of Beds': 'total_beds',
    'Total Discharges': 'total_discharges',
    'Net Patient Revenue': 'net_patient_revenue',
    'Total Operating Expense': 'total_operating_expenses',
    'Operating Margin Percentage': 'operating_margin',
    # lower-case passthrough variants
    'provider_id': 'provider_id',
    'hospital_name': 'hospital_name',
}

TABLE = 'cms_cost_reports_puf'
SCHEMA = 'hcs_raw'


def load_cms_cost_reports_puf(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Cost Reports PUF data from CSV file."""
    logger.info(f"Loading CMS Cost Reports PUF from {filepath} (year={source_year})")

    source_file = Path(filepath).name
    hash_md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    source_hash = hash_md5.hexdigest()

    with get_cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM {SCHEMA}.{TABLE} WHERE _source_hash = %s",
            (source_hash,)
        )
        if cur.fetchone()[0] > 0:
            logger.info(f"File {source_file} already loaded. Skipping.")
            return {"status": "skipped", "records_fetched": 0, "records_inserted": 0, "records_updated": 0, "errors": []}

    df = pd.read_csv(filepath, dtype=str, low_memory=False)
    df = apply_column_mapping(df, COLUMN_MAPPING)
    records_fetched = len(df)

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        try:
            rec = CMSCostReportsPUFRecord(
                provider_id=row.get('provider_id'),
                hospital_name=row.get('hospital_name'),
                city=row.get('city'),
                state=row.get('state'),
                zip_code=row.get('zip_code'),
                fiscal_year_begin=row.get('fiscal_year_begin') or None,
                fiscal_year_end=row.get('fiscal_year_end') or None,
                total_beds=int(float(row['total_beds'])) if pd.notna(row.get('total_beds')) else None,
                total_discharges=int(float(row['total_discharges'])) if pd.notna(row.get('total_discharges')) else None,
                net_patient_revenue=row.get('net_patient_revenue') or None,
                total_operating_expenses=row.get('total_operating_expenses') or None,
                operating_margin=row.get('operating_margin') or None,
                _source_year=source_year,
            )
            d = rec.model_dump(by_alias=True)
            d['_source_hash'] = source_hash
            d['_source_file'] = source_file
            d['_loaded_at'] = loaded_at
            d['_source_year'] = source_year
            records.append(d)
        except (ValidationError, Exception) as e:
            errors.append(f"Row {idx}: {e}")

    inserted = upsert_records(
        SCHEMA, TABLE, records,
        conflict_columns=['provider_id', 'fiscal_year_begin', '_source_year'],
        update_columns=['hospital_name', 'total_beds', 'total_discharges',
                        'net_patient_revenue', 'total_operating_expenses',
                        'operating_margin', '_loaded_at'],
    )

    logger.info(f"Cost Reports PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
