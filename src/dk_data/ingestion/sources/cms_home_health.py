"""CMS Home Health Agency PUF loader. Loads to hcs_raw.cms_home_health."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSHomeHealthRecord

logger = logging.getLogger(__name__)

# Exact CMS Home Health PUF column names -> internal snake_case names
COLUMN_MAPPING = {
    'Rndrng_Prvdr_Id':          'provider_id',
    'Rndrng_Prvdr_Name':        'provider_name',
    'Rndrng_Prvdr_City':        'provider_city',
    'Rndrng_Prvdr_State_Abrvtn':'provider_state',
    'Rndrng_Prvdr_Zip5':        'provider_zip5',
    'HH_Srvc_Cd':               'hh_srvc_cd',
    'HH_Srvc_Desc':             'hh_srvc_desc',
    'Tot_Epsd_Stay':            'tot_epsd_stay',
    'Tot_Benes':                'tot_benes',
    'Avg_HH_Mdcr_Pymt_Amt':    'avg_hh_mdcr_pymt_amt',
    'Avg_HH_Outlier_Pymt':     'avg_hh_outlier_pymt',
    'Avg_Age':                  'avg_age',
    'Female_Pct':               'female_pct',
    'Dual_Pct':                 'dual_pct',
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
    df = apply_column_mapping(df, COLUMN_MAPPING)
    records_fetched = len(df)

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        try:
            rec = CMSHomeHealthRecord(
                provider_id=row.get('provider_id'),
                provider_name=row.get('provider_name'),
                provider_city=row.get('provider_city'),
                provider_state=row.get('provider_state'),
                provider_zip5=row.get('provider_zip5'),
                hh_srvc_cd=row.get('hh_srvc_cd'),
                hh_srvc_desc=row.get('hh_srvc_desc'),
                tot_epsd_stay=int(float(row['tot_epsd_stay'])) if pd.notna(row.get('tot_epsd_stay')) else None,
                tot_benes=int(float(row['tot_benes'])) if pd.notna(row.get('tot_benes')) else None,
                avg_hh_mdcr_pymt_amt=row.get('avg_hh_mdcr_pymt_amt') or None,
                avg_hh_outlier_pymt=row.get('avg_hh_outlier_pymt') or None,
                avg_age=row.get('avg_age') or None,
                female_pct=row.get('female_pct') or None,
                dual_pct=row.get('dual_pct') or None,
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
        conflict_columns=['provider_id', 'hh_srvc_cd', '_source_year'],
        update_columns=[
            'tot_epsd_stay', 'tot_benes', 'avg_hh_mdcr_pymt_amt',
            'avg_hh_outlier_pymt', 'avg_age', 'female_pct', 'dual_pct', '_loaded_at',
        ],
    )

    logger.info(f"Home Health load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
