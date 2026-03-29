"""CMS Inpatient PUF loader (provider-level charge data). Loads to hcs_raw.cms_inpatient_puf."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSInpatientPUFRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    # Legacy CMS format (pre-2021)
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
    # Current CMS format (post-2021) — matches canonical API column names
    # UUID ee6fb1a5 returns provider-level summaries (no DRG breakdown).
    # drg_cd / drg_definition will be NULL for records from this UUID.
    'DRG_Cd': 'drg_cd',
    'DRG_Desc': 'drg_definition',
    'Rndrng_Prvdr_Id': 'provider_id',
    'Rndrng_Prvdr_CCN': 'provider_id',
    'Rndrng_Prvdr_Org_Name': 'provider_name',
    'Rndrng_Prvdr_Name': 'provider_name',
    'Rndrng_Prvdr_St': 'provider_street_address',
    'Rndrng_Prvdr_City': 'provider_city',
    'Rndrng_Prvdr_State_Abrvtn': 'provider_state',
    'Rndrng_Prvdr_State_FIPS': 'provider_state_fips',
    'Rndrng_Prvdr_Zip5': 'provider_zip_code',
    'Rndrng_Prvdr_RUCA': 'provider_ruca',
    'Tot_Dschrgs': 'total_discharges',
    # Confirmed API column names (GET /data-api/v1/dataset/ee6fb1a5/.../data?size=2, 2026-03-29):
    # API returns total-level aggregates, not per-discharge averages.
    'Avg_Submtd_Cvrd_Chrg': 'average_covered_charges',   # DRG-level dataset variant
    'Tot_Submtd_Cvrd_Chrg': 'average_covered_charges',   # Provider-level dataset (UUID ee6fb1a5)
    'Avg_Tot_Pymt_Amt': 'average_total_payments',
    'Tot_Pymt_Amt': 'average_total_payments',
    'Avg_Mdcr_Pymt_Amt': 'average_medicare_payments',
    'Tot_Mdcr_Pymt_Amt': 'average_medicare_payments',
}

TABLE = 'cms_inpatient_puf'
SCHEMA = 'hcs_raw'


def load_cms_inpatient_puf(filepath: str, source_year: int = 2023, max_records: int = 0) -> dict:
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

    df = pd.read_csv(filepath, dtype=str, low_memory=False, nrows=max_records if max_records > 0 else None)
    df = apply_column_mapping(df, COLUMN_MAPPING)
    records_fetched = len(df)

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        try:
            rec = CMSInpatientPUFRecord(
                drg_cd=row.get('drg_cd'),
                drg_definition=row.get('drg_definition'),
                provider_id=row.get('provider_id'),
                provider_name=row.get('provider_name'),
                provider_street_address=row.get('provider_street_address'),
                provider_city=row.get('provider_city'),
                provider_state=row.get('provider_state'),
                provider_state_fips=row.get('provider_state_fips'),
                provider_zip_code=row.get('provider_zip_code'),
                provider_ruca=row.get('provider_ruca'),
                hospital_referral_region_desc=row.get('hospital_referral_region_description'),
                total_discharges=int(float(row['total_discharges'])) if row.get('total_discharges') else None,
                average_covered_charges=row.get('average_covered_charges') or None,
                average_total_payments=row.get('average_total_payments') or None,
                average_medicare_payments=row.get('average_medicare_payments') or None,
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

    # drg_definition is NULL for provider-level records (UUID ee6fb1a5 has no DRG breakdown).
    # Use _source_hash as surrogate conflict key to avoid NULL-in-unique-index issues.
    inserted = upsert_records(
        SCHEMA, TABLE, records,
        conflict_columns=['_source_hash', 'provider_id'],
        update_columns=['_loaded_at'],
    ) if records else 0

    logger.info(f"Inpatient PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
