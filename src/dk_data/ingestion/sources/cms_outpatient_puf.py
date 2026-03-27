"""CMS Outpatient PUF loader (hospital APC-level charges). Loads to hcs_raw.cms_outpatient_puf."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSOutpatientRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Provider Id': 'provider_id',
    'Provider Name': 'provider_name',
    'Provider Street Address': 'provider_street_address',
    'Provider City': 'provider_city',
    'Provider State': 'provider_state',
    'Provider Zip Code': 'provider_zip_code',
    'APC': 'apc',
    'Outpatient Services': 'outpatient_services',
    'Average Estimated Submitted Charges': 'average_estimated_submitted_charges',
    'Average Total Payments': 'average_total_payments',
    # newer CMS format
    'Rndrng_Prvdr_CCN': 'provider_id',
    'Rndrng_Prvdr_Org_Name': 'provider_name',
    'Rndrng_Prvdr_State_Abrvtn': 'provider_state',
    'Rndrng_Prvdr_Zip5': 'provider_zip_code',
    'APC_Cd': 'apc',
    'Tot_Srvcs': 'outpatient_services',
    'Avg_Submtd_Cvrd_Chrg': 'average_estimated_submitted_charges',
    'Avg_Tot_Pymt_Amt': 'average_total_payments',
}

TABLE = 'cms_outpatient_puf'
SCHEMA = 'hcs_raw'


def load_cms_outpatient_puf(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Outpatient PUF charge data from CSV file."""
    logger.info(f"Loading CMS Outpatient PUF from {filepath} (year={source_year})")

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
    df = df.rename(columns=COLUMN_MAPPING)
    records_fetched = len(df)

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        try:
            rec = CMSOutpatientRecord(
                provider_id=row.get('provider_id'),
                provider_name=row.get('provider_name'),
                provider_street_address=row.get('provider_street_address'),
                provider_city=row.get('provider_city'),
                provider_state=row.get('provider_state'),
                provider_zip_code=row.get('provider_zip_code'),
                apc=row.get('apc'),
                outpatient_services=int(row['outpatient_services']) if row.get('outpatient_services') else None,
                average_estimated_submitted_charges=row.get('average_estimated_submitted_charges') or None,
                average_total_payments=row.get('average_total_payments') or None,
                _source_year=source_year,
            )
            d = rec.model_dump(by_alias=True)
            d['_source_hash'] = source_hash
            d['_source_file'] = source_file
            d['_loaded_at'] = loaded_at
            records.append(d)
        except (ValidationError, Exception) as e:
            errors.append(f"Row {idx}: {e}")

    inserted = upsert_records(
        SCHEMA, TABLE, records,
        conflict_columns=['_source_hash', 'provider_id', 'apc', '_source_year'],
        update_columns=['outpatient_services', 'average_estimated_submitted_charges',
                        'average_total_payments', '_loaded_at'],
    )

    logger.info(f"Outpatient PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
