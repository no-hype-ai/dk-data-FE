"""CMS Part B Drug Spending loader. Loads to hcs_raw.cms_part_b_spending."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSPartBSpendingRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'HCPCS_Cd': 'hcpcs_cd',
    'HCPCS_Desc': 'hcpcs_desc',
    'HCPCS_Drug_Ind': 'hcpcs_drug_indicator',
    'Tot_Mftr': 'tot_mftr',
    'Tot_Clms': 'tot_clms',
    'Tot_Allowed_Amt': 'tot_allowed_amt',
    'Tot_Mdcr_Pymt_Amt': 'tot_mdcr_pymt_amt',
    'Avg_Mdcr_Pymt_Amt': 'avg_mdcr_pymt_amt',
    'Avg_Mdcr_Allowed_Amt': 'avg_mdcr_allowed_amt',
    # also handle lower-case variants that CMS sometimes ships
    'hcpcs_cd': 'hcpcs_cd',
    'hcpcs_desc': 'hcpcs_desc',
}

TABLE = 'cms_part_b_spending'
SCHEMA = 'hcs_raw'


def load_cms_part_b_spending(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Part B Drug Spending data from CSV file."""
    logger.info(f"Loading CMS Part B Spending from {filepath} (year={source_year})")

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
            rec = CMSPartBSpendingRecord(
                hcpcs_cd=row.get('hcpcs_cd'),
                hcpcs_desc=row.get('hcpcs_desc'),
                hcpcs_drug_indicator=row.get('hcpcs_drug_indicator'),
                tot_mftr=row.get('tot_mftr'),
                tot_clms=row.get('tot_clms') or None,
                tot_allowed_amt=row.get('tot_allowed_amt') or None,
                tot_mdcr_pymt_amt=row.get('tot_mdcr_pymt_amt') or None,
                avg_mdcr_pymt_amt=row.get('avg_mdcr_pymt_amt') or None,
                avg_mdcr_allowed_amt=row.get('avg_mdcr_allowed_amt') or None,
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
        conflict_columns=['_source_hash', 'hcpcs_cd', '_source_year'],
        update_columns=['tot_allowed_amt', 'tot_mdcr_pymt_amt', '_loaded_at'],
    )

    logger.info(f"Part B Spending load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
