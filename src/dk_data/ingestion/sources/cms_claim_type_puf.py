"""CMS Claim Type Utilization PUF loader. Loads to hcs_raw.cms_claim_type_puf.

Raw CMS field names (snake_case mapping):
  Bene_Geo_Lvl → bene_geo_lvl
  Bene_Geo_Desc → bene_geo_desc
  Clm_Type → clm_type
  Clm_Type_Desc → clm_type_desc
  Tot_Clms → tot_clms
  Tot_Benes → tot_benes
  Tot_Mdcr_Pymt_Amt → tot_mdcr_pymt_amt
  Avg_Mdcr_Pymt_Amt → avg_mdcr_pymt_amt
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSClaimTypeRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Bene_Geo_Lvl': 'bene_geo_lvl',
    'Bene_Geo_Desc': 'bene_geo_desc',
    'Clm_Type': 'clm_type',
    'Clm_Type_Desc': 'clm_type_desc',
    'Tot_Clms': 'tot_clms',
    'Tot_Benes': 'tot_benes',
    'Tot_Mdcr_Pymt_Amt': 'tot_mdcr_pymt_amt',
    'Avg_Mdcr_Pymt_Amt': 'avg_mdcr_pymt_amt',
}

TABLE = 'cms_claim_type_puf'
SCHEMA = 'hcs_raw'


def load_cms_claim_type_puf(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Claim Type PUF data from CSV file."""
    logger.info(f"Loading CMS Claim Type PUF from {filepath} (year={source_year})")

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
            rec = CMSClaimTypeRecord(
                bene_geo_lvl=row.get('bene_geo_lvl'),
                bene_geo_desc=row.get('bene_geo_desc'),
                clm_type=row.get('clm_type'),
                clm_type_desc=row.get('clm_type_desc'),
                tot_clms=int(row['tot_clms']) if row.get('tot_clms') else None,
                tot_benes=int(row['tot_benes']) if row.get('tot_benes') else None,
                tot_mdcr_pymt_amt=row.get('tot_mdcr_pymt_amt') or None,
                avg_mdcr_pymt_amt=row.get('avg_mdcr_pymt_amt') or None,
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
        conflict_columns=['bene_geo_lvl', 'clm_type', '_source_year'],
        update_columns=['tot_clms', 'tot_benes', 'tot_mdcr_pymt_amt',
                        'avg_mdcr_pymt_amt', '_loaded_at'],
    )

    logger.info(f"Claim Type PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
