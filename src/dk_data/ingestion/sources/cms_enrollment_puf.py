"""CMS Medicare Enrollment PUF loader. Loads to hcs_raw.cms_enrollment_puf.

Raw CMS field names (snake_case mapping):
  State_Cd → state_cd
  County_Cd → county_cd
  County_Desc → county_desc
  Bene_Demo_Lvl → bene_demo_lvl
  Bene_Demo_Desc → bene_demo_desc
  Bene_Age_Lvl → bene_age_lvl
  Tot_Benes → tot_benes
  Orgnl_Mdcr_Benes → orgnl_mdcr_benes
  MA_Benes → ma_benes
  ESRD_Benes → esrd_benes
  Dsbl_Benes → dsbl_benes
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSEnrollmentRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'State_Cd': 'state_cd',
    'County_Cd': 'county_cd',
    'County_Desc': 'county_desc',
    'Bene_Demo_Lvl': 'bene_demo_lvl',
    'Bene_Demo_Desc': 'bene_demo_desc',
    'Bene_Age_Lvl': 'bene_age_lvl',
    'Tot_Benes': 'tot_benes',
    'Orgnl_Mdcr_Benes': 'orgnl_mdcr_benes',
    'MA_Benes': 'ma_benes',
    'ESRD_Benes': 'esrd_benes',
    'Dsbl_Benes': 'dsbl_benes',
}

TABLE = 'cms_enrollment_puf'
SCHEMA = 'hcs_raw'


def load_cms_enrollment_puf(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Medicare Enrollment PUF data from CSV file."""
    logger.info(f"Loading CMS Enrollment PUF from {filepath} (year={source_year})")

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
            rec = CMSEnrollmentRecord(
                state_cd=row.get('state_cd'),
                county_cd=row.get('county_cd'),
                county_desc=row.get('county_desc'),
                bene_demo_lvl=row.get('bene_demo_lvl'),
                bene_demo_desc=row.get('bene_demo_desc'),
                bene_age_lvl=row.get('bene_age_lvl'),
                tot_benes=int(row['tot_benes']) if row.get('tot_benes') else None,
                orgnl_mdcr_benes=int(row['orgnl_mdcr_benes']) if row.get('orgnl_mdcr_benes') else None,
                ma_benes=int(row['ma_benes']) if row.get('ma_benes') else None,
                esrd_benes=int(row['esrd_benes']) if row.get('esrd_benes') else None,
                dsbl_benes=int(row['dsbl_benes']) if row.get('dsbl_benes') else None,
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
        conflict_columns=['state_cd', 'county_cd', 'bene_demo_lvl', 'bene_age_lvl', '_source_year'],
        update_columns=['tot_benes', 'orgnl_mdcr_benes', 'ma_benes', 'esrd_benes',
                        'dsbl_benes', '_loaded_at'],
    )

    logger.info(f"Enrollment PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
