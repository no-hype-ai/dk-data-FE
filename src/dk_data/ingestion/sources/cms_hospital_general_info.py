"""CMS Hospital General Information PUF loader. Loads to hcs_raw.cms_hospital_general_info.

NOTE: This is a distinct table from hcs_raw.cms_hospital_info (old schema).
This loader targets hcs_raw.cms_hospital_general_info as part of the PUF ingestion pipeline.
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSHospitalGeneralInfoRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Facility ID': 'facility_id',
    'Facility Name': 'facility_name',
    'Address': 'address',
    'City/Town': 'city',
    'State': 'state',
    'ZIP Code': 'zip_code',
    'County/Parish': 'county_name',
    'Telephone Number': 'phone_number',
    'Hospital Type': 'hospital_type',
    'Hospital Ownership': 'hospital_ownership',
    'Emergency Services': 'emergency_services',
    'Hospital overall rating': 'hospital_overall_rating',
    'Hospital overall rating footnote': 'hospital_overall_rating_footnote',
    # alternate casing
    'facility_id': 'facility_id',
    'facility_name': 'facility_name',
}

TABLE = 'cms_hospital_general_info'
SCHEMA = 'hcs_raw'


def load_cms_hospital_general_info(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Hospital General Information PUF from CSV file."""
    logger.info(f"Loading CMS Hospital General Info from {filepath} (year={source_year})")

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
            rec = CMSHospitalGeneralInfoRecord(
                facility_id=row.get('facility_id'),
                facility_name=row.get('facility_name'),
                address=row.get('address'),
                city=row.get('city'),
                state=row.get('state'),
                zip_code=row.get('zip_code'),
                county_name=row.get('county_name'),
                phone_number=row.get('phone_number'),
                hospital_type=row.get('hospital_type'),
                hospital_ownership=row.get('hospital_ownership'),
                emergency_services=row.get('emergency_services'),
                hospital_overall_rating=row.get('hospital_overall_rating'),
                hospital_overall_rating_footnote=row.get('hospital_overall_rating_footnote'),
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
        conflict_columns=['facility_id', '_source_year'],
        update_columns=['facility_name', 'hospital_type', 'hospital_ownership',
                        'hospital_overall_rating', '_loaded_at'],
    )

    logger.info(f"Hospital General Info load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
