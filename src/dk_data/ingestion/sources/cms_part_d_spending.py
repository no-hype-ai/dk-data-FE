"""CMS Part D Drug Spending loader. Loads to hcs_raw.cms_part_d_spending."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSPartDSpendingRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Brnd_Name': 'brnd_name',
    'Gnrc_Name': 'gnrc_name',
    'Mftr_Name': 'mftr_name',
    'Tot_Mftr': 'tot_mftr',
    'Tot_Clms': 'tot_clms',
    'Tot_30day_Fills': 'tot_30day_fills',
    'Tot_Drug_Cst': 'tot_drug_cst',
    'Tot_Benes': 'tot_benes',
    'Avg_Spnd_Per_Clm': 'avg_spnd_per_clm',
    'Avg_Spnd_Per_30day_Fills': 'avg_spnd_per_30day_fills',
    'Avg_Spnd_Per_Bene': 'avg_spnd_per_bene',
}

TABLE = 'cms_part_d_spending'
SCHEMA = 'hcs_raw'


def load_cms_part_d_spending(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Part D Drug Spending data from CSV file."""
    logger.info(f"Loading CMS Part D Spending from {filepath} (year={source_year})")

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
            rec = CMSPartDSpendingRecord(
                brnd_name=row.get('brnd_name'),
                gnrc_name=row.get('gnrc_name'),
                mftr_name=row.get('mftr_name'),
                tot_mftr=row.get('tot_mftr'),
                tot_clms=row.get('tot_clms') or None,
                tot_30day_fills=row.get('tot_30day_fills') or None,
                tot_drug_cst=row.get('tot_drug_cst') or None,
                tot_benes=row.get('tot_benes') or None,
                avg_spnd_per_clm=row.get('avg_spnd_per_clm') or None,
                avg_spnd_per_30day_fills=row.get('avg_spnd_per_30day_fills') or None,
                avg_spnd_per_bene=row.get('avg_spnd_per_bene') or None,
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
        conflict_columns=['_source_hash', 'gnrc_name', '_source_year'],
        update_columns=['tot_clms', 'tot_drug_cst', 'avg_spnd_per_clm', '_loaded_at'],
    )

    logger.info(f"Part D Spending load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
