"""CMS Ordering/Referring Providers PUF loader. Loads to hcs_raw.cms_ordering_providers.

Raw CMS field names (snake_case mapping):
  Rndrng_NPI → rndrng_npi
  Rndrng_Prvdr_Last_Org_Name → rndrng_prvdr_last_org_name
  Rndrng_Prvdr_First_Name → rndrng_prvdr_first_name
  Rndrng_Prvdr_City → rndrng_prvdr_city
  Rndrng_Prvdr_State_Abrvtn → rndrng_prvdr_state_abrvtn
  Rndrng_Prvdr_Zip5 → rndrng_prvdr_zip5
  Rndrng_Prvdr_Type → rndrng_prvdr_type
  Rfrd_NPI → rfrd_npi
  Rfrd_Prvdr_Last_Org_Name → rfrd_prvdr_last_org_name
  Rfrd_Prvdr_Type → rfrd_prvdr_type
  Tot_Srvcs → tot_srvcs
  Tot_Benes → tot_benes
  Tot_Mdcr_Alowd_Amt → tot_mdcr_alowd_amt
  Tot_Mdcr_Pymt_Amt → tot_mdcr_pymt_amt
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSOrderingProviderRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Rndrng_NPI': 'rndrng_npi',
    'Rfrg_NPI': 'rndrng_npi',  # DME-by-referring-provider dataset uses Rfrg_NPI
    'Rndrng_Prvdr_Last_Org_Name': 'rndrng_prvdr_last_org_name',
    'Rfrg_Prvdr_Last_Name_Org': 'rndrng_prvdr_last_org_name',
    'Rndrng_Prvdr_First_Name': 'rndrng_prvdr_first_name',
    'Rfrg_Prvdr_First_Name': 'rndrng_prvdr_first_name',
    'Rndrng_Prvdr_City': 'rndrng_prvdr_city',
    'Rfrg_Prvdr_City': 'rndrng_prvdr_city',
    'Rndrng_Prvdr_State_Abrvtn': 'rndrng_prvdr_state_abrvtn',
    'Rfrg_Prvdr_State_Abrvtn': 'rndrng_prvdr_state_abrvtn',
    'Rndrng_Prvdr_Zip5': 'rndrng_prvdr_zip5',
    'Rfrg_Prvdr_Zip5': 'rndrng_prvdr_zip5',
    'Rndrng_Prvdr_Type': 'rndrng_prvdr_type',
    'Rfrg_Prvdr_Spclty_Desc': 'rndrng_prvdr_type',
    'Rfrd_NPI': 'rfrd_npi',
    'Rfrd_Prvdr_Last_Org_Name': 'rfrd_prvdr_last_org_name',
    'Rfrd_Prvdr_Type': 'rfrd_prvdr_type',
    'Tot_Srvcs': 'tot_srvcs',
    'Tot_Suplr_Srvcs': 'tot_srvcs',
    'Tot_Benes': 'tot_benes',
    'Tot_Suplr_Benes': 'tot_benes',
    'Tot_Mdcr_Alowd_Amt': 'tot_mdcr_alowd_amt',
    'Suplr_Mdcr_Alowd_Amt': 'tot_mdcr_alowd_amt',
    'Tot_Mdcr_Pymt_Amt': 'tot_mdcr_pymt_amt',
    'Suplr_Mdcr_Pymt_Amt': 'tot_mdcr_pymt_amt',
}

TABLE = 'cms_ordering_providers'
SCHEMA = 'hcs_raw'


def load_cms_ordering_providers(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Ordering/Referring Providers PUF data from CSV file."""
    logger.info(f"Loading CMS Ordering Providers from {filepath} (year={source_year})")

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

    df = pd.read_csv(filepath, dtype={'Rndrng_NPI': str, 'Rfrd_NPI': str,
                                      'Rndrng_Prvdr_Zip5': str}, low_memory=False)
    df = df.rename(columns=COLUMN_MAPPING)
    records_fetched = len(df)

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        try:
            rec = CMSOrderingProviderRecord(
                rndrng_npi=row.get('rndrng_npi'),
                rndrng_prvdr_last_org_name=row.get('rndrng_prvdr_last_org_name'),
                rndrng_prvdr_first_name=row.get('rndrng_prvdr_first_name'),
                rndrng_prvdr_city=row.get('rndrng_prvdr_city'),
                rndrng_prvdr_state_abrvtn=row.get('rndrng_prvdr_state_abrvtn'),
                rndrng_prvdr_zip5=row.get('rndrng_prvdr_zip5'),
                rndrng_prvdr_type=row.get('rndrng_prvdr_type'),
                rfrd_npi=row.get('rfrd_npi'),
                rfrd_prvdr_last_org_name=row.get('rfrd_prvdr_last_org_name'),
                rfrd_prvdr_type=row.get('rfrd_prvdr_type'),
                tot_srvcs=row.get('tot_srvcs') or None,
                tot_benes=int(float(row['tot_benes'])) if pd.notna(row.get('tot_benes')) else None,
                tot_mdcr_alowd_amt=row.get('tot_mdcr_alowd_amt') or None,
                tot_mdcr_pymt_amt=row.get('tot_mdcr_pymt_amt') or None,
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
        conflict_columns=['rndrng_npi', 'rfrd_npi', '_source_year'],
        update_columns=['tot_srvcs', 'tot_benes', 'tot_mdcr_alowd_amt',
                        'tot_mdcr_pymt_amt', '_loaded_at'],
    )

    logger.info(f"Ordering Providers load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
