"""CMS Opioid Prescribing Map PUF loader. Loads to hcs_raw.cms_opioid_puf."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSOpioidRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Prscrbr_NPI': 'prscrbr_npi',
    'Prscrbr_Last_Org_Name': 'prscrbr_last_org_name',
    'Prscrbr_First_Name': 'prscrbr_first_name',
    'Prscrbr_Type': 'prscrbr_type',
    'Prscrbr_State_Abrvtn': 'prscrbr_state_abrvtn',
    'Opioid_Drug_Flag': 'opioid_drug_flag',
    'Extended_Release_Opioid_Drug_Flag': 'extended_release_opioid_drug_flag',
    'Tot_Clms': 'tot_clms',
    'Tot_Opioid_Clms': 'tot_opioid_clms',
    'Opioid_Prscrbr_Rate': 'opioid_prscrbr_rate',
    'Tot_Benes': 'tot_benes',
}

TABLE = 'cms_opioid_puf'
SCHEMA = 'hcs_raw'


def load_cms_opioid_puf(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Opioid Prescribing Map PUF data from CSV file."""
    logger.info(f"Loading CMS Opioid PUF from {filepath} (year={source_year})")

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
            rec = CMSOpioidRecord(
                prscrbr_npi=row.get('prscrbr_npi'),
                prscrbr_last_org_name=row.get('prscrbr_last_org_name'),
                prscrbr_first_name=row.get('prscrbr_first_name'),
                prscrbr_type=row.get('prscrbr_type'),
                prscrbr_state_abrvtn=row.get('prscrbr_state_abrvtn'),
                opioid_drug_flag=row.get('opioid_drug_flag'),
                extended_release_opioid_drug_flag=row.get('extended_release_opioid_drug_flag'),
                tot_clms=int(row['tot_clms']) if row.get('tot_clms') else None,
                tot_opioid_clms=int(row['tot_opioid_clms']) if row.get('tot_opioid_clms') else None,
                opioid_prscrbr_rate=row.get('opioid_prscrbr_rate') or None,
                tot_benes=int(row['tot_benes']) if row.get('tot_benes') else None,
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
        conflict_columns=['_source_hash', 'prscrbr_npi', '_source_year'],
        update_columns=['tot_clms', 'tot_opioid_clms', 'opioid_prscrbr_rate', '_loaded_at'],
    )

    logger.info(f"Opioid PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
