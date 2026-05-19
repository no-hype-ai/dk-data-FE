"""CMS Medicare Advantage enrollment loader. Loads to hcs_raw.cms_medicare_advantage.

Dataset: Medicare Advantage Geographic Variation (UUID 8e989bc0-2260-49a7-9c6d-8e9e10af7cea).

Confirmed API columns (GET /data-api/v1/dataset/{uuid}/data?size=2, 2026-03-29):
  YEAR, STATE, BENE_GEO_LVL, BENE_GEO_CD, BENE_GEO_DESC, BENES_MA_CNT, etc.

NOTE: This dataset contains geographic-level MA enrollment aggregates, NOT plan-level
enrollment data.  Plan-level columns (Cntrct_ID, Org_Name, Plan_ID, Plan_Name,
Avg_Age, Star_Rating etc.) do not exist in this source — those fields will be NULL.
The DB unique constraint includes contract_id/plan_id which are NULL here, so
ON CONFLICT cannot be used.  INSERT ... ON CONFLICT DO NOTHING is used instead.
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSMedicareAdvantageRecord

logger = logging.getLogger(__name__)

# Canonical CMS column names → internal snake_case names.
# UUID 8e989bc0 returns geographic enrollment data, not plan-level data.
# Actual API columns: YEAR, STATE, BENE_GEO_LVL, BENE_GEO_CD, BENE_GEO_DESC,
#   BENES_MA_CNT, BENES_AB_CNT, BENES_FFS_CNT, etc.
# Plan-level columns (Cntrct_ID, Org_Name, Plan_ID etc.) are NOT returned by this UUID.
COLUMN_MAPPING = {
    # Geographic enrollment API columns (UUID 8e989bc0)
    'YEAR':                   'enrollment_data_period',
    'STATE':                  'state_fips',
    'BENE_STATE_ABRVTN':      'state_fips',
    'BENE_GEO_CD':            'county_fips',
    'BENE_GEO_LVL':           'fips_cd',
    'BENES_MA_CNT':           'enrollment',
    'BENES_AB_CNT':           'enrollment',     # alternate enrollment column
    # Plan-level columns — present in plan-level variant of this dataset
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
    'Segment_ID':             'segment_id',
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


def load_cms_medicare_advantage(filepath: Optional[str] = None, rows: Optional[List[Dict]] = None, source_year: int = 2023, max_records: int = 0, source_hash: Optional[str] = None) -> dict:
    """Load CMS Medicare Advantage enrollment data from CSV file."""
    logger.info(f"Loading CMS Medicare Advantage (year={source_year})")

    if rows is not None:
        # Streaming mode: rows passed directly from API, no file needed
        normalized = [{k: ('' if v is None else str(v)) for k, v in row.items()} for row in rows]
        df = pd.DataFrame(normalized) if normalized else pd.DataFrame()
        _source_hash = source_hash or f"api_stream_{source_year}"
        source_file = f"api_stream_{source_year}"
    else:
        if filepath is None:
            raise ValueError("Either filepath or rows must be provided")
        source_file = Path(filepath).name
        hash_md5 = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_md5.update(chunk)
        _source_hash = source_hash or hash_md5.hexdigest()

        with get_cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM {SCHEMA}.{TABLE} WHERE _source_hash = %s",
                (_source_hash,)
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
            d['_source_hash'] = _source_hash
            d['_source_file'] = source_file
            d['_loaded_at'] = loaded_at
            d['_source_year'] = source_year
            records.append(d)
        except (ValidationError, Exception) as e:
            errors.append(f"Row {idx}: {e}")

    # Use _source_hash as surrogate conflict key to avoid NULL-in-unique-index issues.
    # (contract_id/plan_id are NULL for geographic-level MA data.)
    inserted = upsert_records(
        SCHEMA, TABLE, records,
        conflict_columns=['_source_hash', 'enrollment_data_period', 'fips_cd'],
        update_columns=['_loaded_at'],
    ) if records else 0

    logger.info(f"Medicare Advantage load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
