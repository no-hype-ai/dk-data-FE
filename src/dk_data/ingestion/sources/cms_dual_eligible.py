"""CMS Dual Eligible Beneficiary loader. Loads to hcs_raw.cms_dual_eligible.

Raw CMS field names (snake_case mapping):
  State_Cd → state_cd
  State_Name → state_name
  Dual_Elgbl_Lvl → dual_elgbl_lvl
  Dual_Elgbl_Desc → dual_elgbl_desc
  Tot_Benes → tot_benes
  FFS_Benes → ffs_benes
  MA_Benes → ma_benes
  Dual_Elgbl_Full_Benes → dual_elgbl_full_benes
  Dual_Elgbl_Prtl_Benes → dual_elgbl_prtl_benes
  Non_Dual_Benes → non_dual_benes
  LIS_Benes → lis_benes
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSDualEligibleRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'State_Cd': 'state_cd',
    'State_Name': 'state_name',
    'Dual_Elgbl_Lvl': 'dual_elgbl_lvl',
    'Dual_Elgbl_Desc': 'dual_elgbl_desc',
    'Tot_Benes': 'tot_benes',
    'FFS_Benes': 'ffs_benes',
    'MA_Benes': 'ma_benes',
    'Dual_Elgbl_Full_Benes': 'dual_elgbl_full_benes',
    'Dual_Elgbl_Prtl_Benes': 'dual_elgbl_prtl_benes',
    'Non_Dual_Benes': 'non_dual_benes',
    'LIS_Benes': 'lis_benes',
}

TABLE = 'cms_dual_eligible'
SCHEMA = 'hcs_raw'


def load_cms_dual_eligible(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Dual Eligible beneficiary data from CSV file."""
    logger.info(f"Loading CMS Dual Eligible from {filepath} (year={source_year})")

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
            rec = CMSDualEligibleRecord(
                state_cd=row.get('state_cd'),
                state_name=row.get('state_name'),
                dual_elgbl_lvl=row.get('dual_elgbl_lvl'),
                dual_elgbl_desc=row.get('dual_elgbl_desc'),
                tot_benes=int(float(row['tot_benes'])) if pd.notna(row.get('tot_benes')) else None,
                ffs_benes=int(float(row['ffs_benes'])) if pd.notna(row.get('ffs_benes')) else None,
                ma_benes=int(float(row['ma_benes'])) if pd.notna(row.get('ma_benes')) else None,
                dual_elgbl_full_benes=int(float(row['dual_elgbl_full_benes'])) if pd.notna(row.get('dual_elgbl_full_benes')) else None,
                dual_elgbl_prtl_benes=int(float(row['dual_elgbl_prtl_benes'])) if pd.notna(row.get('dual_elgbl_prtl_benes')) else None,
                non_dual_benes=int(float(row['non_dual_benes'])) if pd.notna(row.get('non_dual_benes')) else None,
                lis_benes=int(float(row['lis_benes'])) if pd.notna(row.get('lis_benes')) else None,
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
        conflict_columns=['state_cd', 'dual_elgbl_lvl', '_source_year'],
        update_columns=['tot_benes', 'ffs_benes', 'ma_benes', 'dual_elgbl_full_benes',
                        'dual_elgbl_prtl_benes', 'non_dual_benes', 'lis_benes', '_loaded_at'],
    )

    logger.info(f"Dual Eligible load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
