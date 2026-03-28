"""CMS Skilled Nursing Facility (SNF) PUF loader. Loads to hcs_raw.cms_snf_puf."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSSNFRecord

logger = logging.getLogger(__name__)

# Exact CMS SNF PUF column names -> internal snake_case names
# CMS SNF PUF grain: provider × RUG code × year
COLUMN_MAPPING = {
    'Rndrng_Prvdr_Id':          'provider_id',
    'Rndrng_Prvdr_Name':        'provider_name',
    'Rndrng_Prvdr_City':        'provider_city',
    'Rndrng_Prvdr_State_Abrvtn':'provider_state',
    'Rndrng_Prvdr_Zip5':        'provider_zip5',
    'RUG_CD':                   'rug_cd',
    'RUG_DESC':                 'rug_desc',
    'Tot_Benes':                'tot_benes',
    'Tot_Cvrd_Days':            'tot_cvrd_days',
    'Avg_Cvrd_Days':            'avg_cvrd_days',
    'Tot_Mdcr_Alowd_Amt':       'tot_mdcr_alowd_amt',
    'Avg_Mdcr_Alowd_Amt':       'avg_mdcr_alowd_amt',
    'Tot_Mdcr_Pymt_Amt':        'tot_mdcr_pymt_amt',
    'Avg_Mdcr_Pymt_Amt':        'avg_mdcr_pymt_amt',
}

TABLE = 'cms_snf_puf'
SCHEMA = 'hcs_raw'


def load_cms_snf_puf(filepath: str, source_year: int = 2023) -> dict:
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

    df = pd.read_csv(filepath, dtype=str, low_memory=False)
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
                rug_cd=row.get('rug_cd'),
                rug_desc=row.get('rug_desc'),
                tot_benes=int(float(row['tot_benes'])) if pd.notna(row.get('tot_benes')) else None,
                tot_cvrd_days=int(float(row['tot_cvrd_days'])) if pd.notna(row.get('tot_cvrd_days')) else None,
                avg_cvrd_days=row.get('avg_cvrd_days') or None,
                tot_mdcr_alowd_amt=row.get('tot_mdcr_alowd_amt') or None,
                avg_mdcr_alowd_amt=row.get('avg_mdcr_alowd_amt') or None,
                tot_mdcr_pymt_amt=row.get('tot_mdcr_pymt_amt') or None,
                avg_mdcr_pymt_amt=row.get('avg_mdcr_pymt_amt') or None,
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
