"""CMS Durable Medical Equipment (DME) PUF loader. Loads to hcs_raw.cms_dme_puf."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSDMERecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    'Rndrng_NPI': 'npi',
    'Rndrng_Prvdr_Last_Org_Name': 'provider_last_org_name',
    'Rndrng_Prvdr_First_Name': 'provider_first_name',
    'Rndrng_Prvdr_Type': 'provider_type',
    'Rndrng_Prvdr_State_Abrvtn': 'provider_state',
    'HCPCS_Cd': 'hcpcs_cd',
    'HCPCS_Desc': 'hcpcs_desc',
    'Bene_Unique_Cnt': 'bene_unique_cnt',
    'Tot_Suplrs': 'total_suplrs',
    'Suplr_Rental_Ind': 'suplr_rental_ind',
    'Tot_Suplr_Sbmtd_Chrg': 'tot_suplr_sbmtd_chrg',
    'Tot_Suplr_Mdcr_Alowd_Amt': 'tot_suplr_mdcr_alowd_amt',
    'Tot_Suplr_Mdcr_Pymt_Amt': 'tot_suplr_mdcr_pymt_amt',
}

TABLE = 'cms_dme_puf'
SCHEMA = 'hcs_raw'


def load_cms_dme_puf(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS DME PUF data from CSV file."""
    logger.info(f"Loading CMS DME PUF from {filepath} (year={source_year})")

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
            rec = CMSDMERecord(
                npi=row.get('npi'),
                provider_last_org_name=row.get('provider_last_org_name'),
                provider_first_name=row.get('provider_first_name'),
                provider_type=row.get('provider_type'),
                provider_state=row.get('provider_state'),
                hcpcs_cd=row.get('hcpcs_cd'),
                hcpcs_desc=row.get('hcpcs_desc'),
                bene_unique_cnt=int(row['bene_unique_cnt']) if row.get('bene_unique_cnt') else None,
                total_suplrs=int(row['total_suplrs']) if row.get('total_suplrs') else None,
                suplr_rental_ind=row.get('suplr_rental_ind'),
                tot_suplr_sbmtd_chrg=row.get('tot_suplr_sbmtd_chrg') or None,
                tot_suplr_mdcr_alowd_amt=row.get('tot_suplr_mdcr_alowd_amt') or None,
                tot_suplr_mdcr_pymt_amt=row.get('tot_suplr_mdcr_pymt_amt') or None,
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
        conflict_columns=['_source_hash', 'npi', 'hcpcs_cd', '_source_year'],
        update_columns=['bene_unique_cnt', 'tot_suplr_mdcr_alowd_amt', 'tot_suplr_mdcr_pymt_amt', '_loaded_at'],
    )

    logger.info(f"DME PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
