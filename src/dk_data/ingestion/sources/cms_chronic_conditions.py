"""CMS Chronic Conditions PUF loader. Loads to hcs_raw.cms_chronic_conditions."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSChronicConditionsRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Bene_Geo_Lvl': 'bene_geo_lvl',
    'Bene_State_Abrvtn': 'bene_state_abrvtn',
    'Bene_State_Desc': 'bene_state_desc',
    'Bene_County_Desc': 'bene_county_desc',
    'Bene_FIPS_Cd': 'bene_fips_cd',
    'Bene_Age_Lvl': 'bene_age_lvl',
    'Bene_Sex_Cd': 'bene_sex_cd',
    'Bene_Race_Cd': 'bene_race_cd',
    'Bene_Dual_Stus_Cd': 'bene_dual_stus_cd',
    'Chronic_Condition': 'chronic_condition',
    'Prevalence': 'prevalence',
}

TABLE = 'cms_chronic_conditions'
SCHEMA = 'hcs_raw'


def load_cms_chronic_conditions(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Chronic Conditions PUF data from CSV file."""
    logger.info(f"Loading CMS Chronic Conditions from {filepath} (year={source_year})")

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
            rec = CMSChronicConditionsRecord(
                bene_geo_lvl=row.get('bene_geo_lvl'),
                bene_state_abrvtn=row.get('bene_state_abrvtn'),
                bene_state_desc=row.get('bene_state_desc'),
                bene_county_desc=row.get('bene_county_desc'),
                bene_fips_cd=row.get('bene_fips_cd'),
                bene_age_lvl=row.get('bene_age_lvl'),
                bene_sex_cd=row.get('bene_sex_cd'),
                bene_race_cd=row.get('bene_race_cd'),
                bene_dual_stus_cd=row.get('bene_dual_stus_cd'),
                chronic_condition=row.get('chronic_condition'),
                prevalence=row.get('prevalence') or None,
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
        conflict_columns=['_source_hash', 'bene_fips_cd', 'chronic_condition',
                          'bene_age_lvl', 'bene_sex_cd', '_source_year'],
        update_columns=['prevalence', '_loaded_at'],
    )

    logger.info(f"Chronic Conditions load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
