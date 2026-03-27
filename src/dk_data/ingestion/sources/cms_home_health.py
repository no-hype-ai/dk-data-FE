"""CMS Home Health Agency PUF loader. Loads to hcs_raw.cms_home_health."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSHomeHealthRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'CMS Certification Number (CCN)': 'provider_id',
    'Agency Name': 'agency_name',
    'Street Address': 'street_address',
    'City': 'city',
    'State': 'state',
    'Zip Code': 'zip_code',
    'Tot_Epis': 'tot_epis',
    'Tot_HHA_Mdcr_Pymt_Amt': 'tot_hha_mdcr_pymt_amt',
    'Avg_HHA_Mdcr_Pymt_Amt': 'avg_hha_mdcr_pymt_amt',
    'Tot_Benes': 'tot_benes',
    # snake_case variants
    'provider_id': 'provider_id',
    'agency_name': 'agency_name',
}

TABLE = 'cms_home_health'
SCHEMA = 'hcs_raw'


def load_cms_home_health(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Home Health Agency PUF data from CSV file."""
    logger.info(f"Loading CMS Home Health from {filepath} (year={source_year})")

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
            rec = CMSHomeHealthRecord(
                provider_id=row.get('provider_id'),
                agency_name=row.get('agency_name'),
                street_address=row.get('street_address'),
                city=row.get('city'),
                state=row.get('state'),
                zip_code=row.get('zip_code'),
                tot_epis=int(row['tot_epis']) if row.get('tot_epis') else None,
                tot_hha_mdcr_pymt_amt=row.get('tot_hha_mdcr_pymt_amt') or None,
                avg_hha_mdcr_pymt_amt=row.get('avg_hha_mdcr_pymt_amt') or None,
                tot_benes=int(row['tot_benes']) if row.get('tot_benes') else None,
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
        conflict_columns=['provider_id', '_source_year'],
        update_columns=['tot_epis', 'tot_hha_mdcr_pymt_amt', 'avg_hha_mdcr_pymt_amt', 'tot_benes', '_loaded_at'],
    )

    logger.info(f"Home Health load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
