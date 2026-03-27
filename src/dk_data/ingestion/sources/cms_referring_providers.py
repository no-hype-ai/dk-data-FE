"""CMS Referring Providers PUF loader. Loads to hcs_raw.cms_referring_providers."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSReferringProviderRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Rndrng_NPI': 'rndrng_npi',
    'Rfr_NPI': 'rfr_npi',
    'Rfr_Prvdr_Last_Org_Name': 'rfr_prvdr_last_org_name',
    'Rfr_Prvdr_First_Name': 'rfr_prvdr_first_name',
    'Rfr_Prvdr_Type': 'rfr_prvdr_type',
    'Rfr_Prvdr_State_Abrvtn': 'rfr_prvdr_state_abrvtn',
    'Tot_Rndrng_Prvdrs': 'tot_rndrng_prvdrs',
    'Tot_Srvcs': 'tot_srvcs',
    'Tot_Mdcr_Alowd_Amt': 'tot_mdcr_alowd_amt',
    'Tot_Mdcr_Pymt_Amt': 'tot_mdcr_pymt_amt',
}

TABLE = 'cms_referring_providers'
SCHEMA = 'hcs_raw'


def load_cms_referring_providers(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Referring Providers PUF data from CSV file."""
    logger.info(f"Loading CMS Referring Providers from {filepath} (year={source_year})")

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
            rec = CMSReferringProviderRecord(
                rndrng_npi=row.get('rndrng_npi'),
                rfr_npi=row.get('rfr_npi'),
                rfr_prvdr_last_org_name=row.get('rfr_prvdr_last_org_name'),
                rfr_prvdr_first_name=row.get('rfr_prvdr_first_name'),
                rfr_prvdr_type=row.get('rfr_prvdr_type'),
                rfr_prvdr_state_abrvtn=row.get('rfr_prvdr_state_abrvtn'),
                tot_rndrng_prvdrs=int(row['tot_rndrng_prvdrs']) if row.get('tot_rndrng_prvdrs') else None,
                tot_srvcs=row.get('tot_srvcs') or None,
                tot_mdcr_alowd_amt=row.get('tot_mdcr_alowd_amt') or None,
                tot_mdcr_pymt_amt=row.get('tot_mdcr_pymt_amt') or None,
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
        conflict_columns=['_source_hash', 'rndrng_npi', 'rfr_npi', '_source_year'],
        update_columns=['tot_srvcs', 'tot_mdcr_alowd_amt', 'tot_mdcr_pymt_amt', '_loaded_at'],
    )

    logger.info(f"Referring Providers load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
