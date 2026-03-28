"""CMS Medicare Advantage enrollment loader. Loads to hcs_raw.cms_medicare_advantage."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSMedicareAdvantageRecord

logger = logging.getLogger(__name__)

# Canonical CMS column names → internal snake_case names.
# Spec fields: Cntrct_ID, Org_Name, Org_Type, Plan_ID, Plan_Name,
# Enrlmt_Data_Prd, Enrlmt_FIPS_Cd, Enrlmt_State_FIPS_Cd, Enrlmt_Cnty_FIPS_Cd,
# Enrlmt, Avg_Age, Pct_Female, Avg_Risk_Scr, MA_Participation_Rate, Star_Rating.
COLUMN_MAPPING = {
    'Cntrct_ID':              'contract_id',
    'Org_Name':               'organization_name',
    'Org_Type':               'organization_type',
    'Plan_ID':                'plan_id',
    'Plan_Name':              'plan_name',
    'Enrlmt_Data_Prd':        'enrollment_data_period',
    'Enrlmt_FIPS_Cd':         'fips_cd',
    'Enrlmt_State_FIPS_Cd':   'state_fips',
    'Enrlmt_Cnty_FIPS_Cd':    'county_fips',
    'Enrlmt':                 'enrollment',
    'Avg_Age':                'avg_age',
    'Pct_Female':             'pct_female',
    'Avg_Risk_Scr':           'avg_risk_score',
    'MA_Participation_Rate':  'ma_participation_rate',
    'Star_Rating':            'star_rating',
    # Supplemental column present in some file variants
    'Segment_ID':             'segment_id',
    # Legacy/alternate header variants (lowercase from older CMS exports)
    'contract_id':            'contract_id',
    'plan_id':                'plan_id',
}

TABLE = 'cms_medicare_advantage'
SCHEMA = 'hcs_raw'


def _safe_int(val) -> int | None:
    """Suppress '*' or blank enrollment values → None."""
    if val is None:
        return None
    s = str(val).strip()
    if s in ('', '*'):
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _safe_decimal(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    if s in ('', '*'):
        return None
    return s


def load_cms_medicare_advantage(filepath: str, source_year: int = 2023, max_records: int = 0) -> dict:
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

    df = pd.read_csv(filepath, dtype=str, low_memory=False, nrows=max_records if max_records > 0 else None)
    df = apply_column_mapping(df, COLUMN_MAPPING)
    records_fetched = len(df)

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        try:
            rec = CMSMedicareAdvantageRecord(
                contract_id=row.get('contract_id'),
                organization_name=row.get('organization_name'),
                organization_type=row.get('organization_type'),
                plan_id=row.get('plan_id'),
                plan_name=row.get('plan_name'),
                segment_id=row.get('segment_id'),
                enrollment_data_period=row.get('enrollment_data_period'),
                fips_cd=row.get('fips_cd'),
                state_fips=row.get('state_fips'),
                county_fips=row.get('county_fips'),
                enrollment=_safe_int(row.get('enrollment')),
                avg_age=_safe_decimal(row.get('avg_age')),
                pct_female=_safe_decimal(row.get('pct_female')),
                avg_risk_score=_safe_decimal(row.get('avg_risk_score')),
                ma_participation_rate=_safe_decimal(row.get('ma_participation_rate')),
                star_rating=_safe_decimal(row.get('star_rating')),
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
        conflict_columns=['_source_hash', 'contract_id', 'plan_id', 'fips_cd', '_source_year'],
        update_columns=[
            'enrollment', 'avg_age', 'pct_female', 'avg_risk_score',
            'ma_participation_rate', 'star_rating', 'plan_name', '_loaded_at',
        ],
    )

    logger.info(f"Medicare Advantage load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
