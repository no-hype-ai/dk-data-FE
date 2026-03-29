"""CMS Skilled Nursing Facility (SNF) PUF loader. Loads to hcs_raw.cms_snf_puf.

Dataset: Medicare Skilled Nursing Facility - by Provider
UUID: eaed338b-847e-41b1-a4d3-a206f40dc72b

Confirmed API columns (GET /data-api/v1/dataset/{uuid}/data?size=2, 2026-03-29):
  YEAR, YEAR_TYPE, SMRY_CTGRY, SRVC_CTGRY, PRVDR_ID, PRVDR_NAME, PRVDR_CITY,
  STATE, PRVDR_ZIP, BENE_DSTNCT_CNT, TOT_EPSD_STAY_CNT, TOT_SRVC_DAYS,
  TOT_CHRG_AMT, TOT_ALOWD_AMT, TOT_MDCR_PYMT_AMT, TOT_MDCR_STDZD_PYMT_AMT,
  BENE_DUAL_PCT, BENE_RRL_PCT, BENE_AVG_AGE, BENE_MALE_PCT, BENE_FEML_PCT,
  (plus many chronic condition and diagnosis category PCT fields)

NOTE: This dataset is provider-level, NOT RUG-code-level.  There are no RUG_CD
or RUG_DESC columns in the API response.  rug_cd and rug_desc will always be NULL.
NOTE: SMRY_CTGRY + SRVC_CTGRY are used as the grain discriminator in place of rug_cd.
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSSNFRecord

logger = logging.getLogger(__name__)

# Exact CMS SNF PUF column names -> internal snake_case names.
# CMS SNF PUF grain: provider × summary_category × service_category × year.
# API uses ALL-CAPS field names; there are NO RUG_CD / RUG_DESC columns.
COLUMN_MAPPING = {
    'PRVDR_ID':                 'provider_id',
    'PRVDR_NAME':               'provider_name',
    'PRVDR_CITY':               'provider_city',
    'STATE':                    'provider_state',
    'PRVDR_ZIP':                'provider_zip5',
    # rug_cd / rug_desc — no RUG columns in this dataset; NULL downstream.
    # Re-use rug_cd to store SMRY_CTGRY so grain uniqueness is preserved.
    'SMRY_CTGRY':               'rug_cd',
    'SRVC_CTGRY':               'rug_desc',
    'BENE_DSTNCT_CNT':          'tot_benes',
    'TOT_SRVC_DAYS':            'tot_cvrd_days',
    # No average covered days column in this dataset.
    'TOT_ALOWD_AMT':            'tot_mdcr_alowd_amt',
    'TOT_MDCR_PYMT_AMT':        'tot_mdcr_pymt_amt',
    # No per-provider average columns; avg_cvrd_days and avg_mdcr_* will be NULL.
}

TABLE = 'cms_snf_puf'
SCHEMA = 'hcs_raw'


def load_cms_snf_puf(filepath: str, source_year: int = 2023, max_records: int = 0) -> dict:
    """Load CMS SNF PUF data from CSV file."""
    logger.info(f"Loading CMS SNF PUF from {filepath} (year={source_year})")

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
            rec = CMSSNFRecord(
                provider_id=row.get('provider_id'),
                provider_name=row.get('provider_name'),
                provider_city=row.get('provider_city'),
                provider_state=row.get('provider_state'),
                provider_zip5=row.get('provider_zip5'),
                # rug_cd stores SMRY_CTGRY; rug_desc stores SRVC_CTGRY
                rug_cd=row.get('rug_cd'),
                rug_desc=row.get('rug_desc'),
                tot_benes=int(float(row['tot_benes'])) if pd.notna(row.get('tot_benes')) else None,
                tot_cvrd_days=int(float(row['tot_cvrd_days'])) if pd.notna(row.get('tot_cvrd_days')) else None,
                avg_cvrd_days=None,  # no average-days column in this dataset
                tot_mdcr_alowd_amt=row.get('tot_mdcr_alowd_amt') or None,
                avg_mdcr_alowd_amt=None,  # no per-provider average in this dataset
                tot_mdcr_pymt_amt=row.get('tot_mdcr_pymt_amt') or None,
                avg_mdcr_pymt_amt=None,  # no per-provider average in this dataset
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
        conflict_columns=['provider_id', 'rug_cd', '_source_year'],
        update_columns=[
            'tot_benes', 'tot_cvrd_days', 'avg_cvrd_days',
            'tot_mdcr_alowd_amt', 'avg_mdcr_alowd_amt',
            'tot_mdcr_pymt_amt', 'avg_mdcr_pymt_amt', '_loaded_at',
        ],
    )

    logger.info(f"SNF PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
