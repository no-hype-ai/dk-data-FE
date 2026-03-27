"""CMS Inpatient PUF loader (provider-level charge data). Loads to hcs_raw.cms_inpatient_puf."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSInpatientPUFRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'DRG Definition': 'drg_definition',
    'Provider Id': 'provider_id',
    'Provider Name': 'provider_name',
    'Provider Street Address': 'provider_street_address',
    'Provider City': 'provider_city',
    'Provider State': 'provider_state',
    'Provider Zip Code': 'provider_zip_code',
    'Hospital Referral Region (HRR) Description': 'hospital_referral_region_description',
    'Total Discharges': 'total_discharges',
    'Average Covered Charges': 'average_covered_charges',
    'Average Total Payments': 'average_total_payments',
    'Average Medicare Payments': 'average_medicare_payments',
    # Newer format column names
    'DRG_Cd': 'drg_definition',
    'Rndrng_Prvdr_CCN': 'provider_id',
    'Rndrng_Prvdr_Org_Name': 'provider_name',
    'Rndrng_Prvdr_State_Abrvtn': 'provider_state',
    'Rndrng_Prvdr_Zip5': 'provider_zip_code',
    'Tot_Dschrgs': 'total_discharges',
    'Avg_Submtd_Cvrd_Chrg': 'average_covered_charges',
    'Avg_Tot_Pymt_Amt': 'average_total_payments',
    'Avg_Mdcr_Pymt_Amt': 'average_medicare_payments',
}

TABLE = 'cms_inpatient_puf'
SCHEMA = 'hcs_raw'


def load_cms_inpatient_puf(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Inpatient PUF charge data from CSV file."""
    logger.info(f"Loading CMS Inpatient PUF from {filepath} (year={source_year})")

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
            rec = CMSInpatientPUFRecord(
                drg_definition=row.get('drg_definition'),
                provider_id=row.get('provider_id'),
                provider_name=row.get('provider_name'),
                provider_street_address=row.get('provider_street_address'),
                provider_city=row.get('provider_city'),
                provider_state=row.get('provider_state'),
                provider_zip_code=row.get('provider_zip_code'),
                hospital_referral_region_description=row.get('hospital_referral_region_description'),
                total_discharges=int(row['total_discharges']) if row.get('total_discharges') else None,
                average_covered_charges=row.get('average_covered_charges') or None,
                average_total_payments=row.get('average_total_payments') or None,
                average_medicare_payments=row.get('average_medicare_payments') or None,
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
        conflict_columns=['_source_hash', 'provider_id', 'drg_definition', '_source_year'],
        update_columns=['total_discharges', 'average_covered_charges', 'average_total_payments',
                        'average_medicare_payments', '_loaded_at'],
    )

    logger.info(f"Inpatient PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
