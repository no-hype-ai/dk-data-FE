"""CMS Medicare Advantage enrollment loader. Loads to hcs_raw.cms_medicare_advantage."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSMedicareAdvantageRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Contract ID': 'contract_id',
    'Plan ID': 'plan_id',
    'Segment ID': 'segment_id',
    'Organization Name': 'organization_name',
    'Organization Type': 'organization_type',
    'Plan Name': 'plan_name',
    'Plan Type': 'plan_type',
    'State': 'state',
    'County Name': 'county_name',
    'County Code': 'county_code',
    'Enrollment': 'enrollment',
    # snake_case variants
    'contract_id': 'contract_id',
    'plan_id': 'plan_id',
}

TABLE = 'cms_medicare_advantage'
SCHEMA = 'hcs_raw'


def load_cms_medicare_advantage(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Medicare Advantage enrollment data from CSV file."""
    logger.info(f"Loading CMS Medicare Advantage from {filepath} (year={source_year})")

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
            rec = CMSMedicareAdvantageRecord(
                contract_id=row.get('contract_id'),
                plan_id=row.get('plan_id'),
                segment_id=row.get('segment_id'),
                organization_name=row.get('organization_name'),
                organization_type=row.get('organization_type'),
                plan_name=row.get('plan_name'),
                plan_type=row.get('plan_type'),
                state=row.get('state'),
                county_name=row.get('county_name'),
                county_code=row.get('county_code'),
                enrollment=int(row['enrollment']) if row.get('enrollment') and str(row['enrollment']).strip() not in ('', '*') else None,
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
        conflict_columns=['_source_hash', 'contract_id', 'plan_id', 'county_code', '_source_year'],
        update_columns=['enrollment', 'plan_name', 'plan_type', '_loaded_at'],
    )

    logger.info(f"Medicare Advantage load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
