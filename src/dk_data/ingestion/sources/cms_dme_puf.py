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

# Exact CMS PUF column names -> internal snake_case names
COLUMN_MAPPING = {
    'Rndrng_NPI':                   'npi',
    'Rndrng_Prvdr_Last_Org_Name':   'provider_last_org_name',
    'Rndrng_Prvdr_First_Name':      'provider_first_name',
    'Rndrng_Prvdr_City':            'provider_city',
    'Rndrng_Prvdr_State_Abrvtn':    'provider_state',
    'Rndrng_Prvdr_State_FIPS':      'provider_state_fips',
    'Rndrng_Prvdr_Zip5':            'provider_zip5',
    'Rndrng_Prvdr_RUCA':            'provider_ruca',
    'Rndrng_Prvdr_Type':            'provider_type',
    'HCPCS_Cd':                     'hcpcs_cd',
    'HCPCS_Desc':                   'hcpcs_desc',
    'Suplr_Rentl_Ind':              'suplr_rentl_ind',
    'Tot_Suplrs':                   'tot_suplrs',
    'Tot_Suplr_Benes':              'tot_suplr_benes',
    'Tot_Suplr_Clms':               'tot_suplr_clms',
    'Tot_Suplr_Srvcs':              'tot_suplr_srvcs',
    'Avg_Suplr_Sbmtd_Chrg':         'avg_suplr_sbmtd_chrg',
    'Avg_Suplr_Mdcr_Alowd_Amt':     'avg_suplr_mdcr_alowd_amt',
    'Avg_Suplr_Mdcr_Pymt_Amt':      'avg_suplr_mdcr_pymt_amt',
    'Avg_Suplr_Mdcr_Stdzd_Amt':     'avg_suplr_mdcr_stdzd_amt',
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
                provider_city=row.get('provider_city'),
                provider_state=row.get('provider_state'),
                provider_state_fips=row.get('provider_state_fips'),
                provider_zip5=row.get('provider_zip5'),
                provider_ruca=row.get('provider_ruca'),
                provider_type=row.get('provider_type'),
                hcpcs_cd=row.get('hcpcs_cd'),
                hcpcs_desc=row.get('hcpcs_desc'),
                suplr_rentl_ind=row.get('suplr_rentl_ind'),
                tot_suplrs=int(row['tot_suplrs']) if row.get('tot_suplrs') else None,
                tot_suplr_benes=int(row['tot_suplr_benes']) if row.get('tot_suplr_benes') else None,
                tot_suplr_clms=int(row['tot_suplr_clms']) if row.get('tot_suplr_clms') else None,
                tot_suplr_srvcs=int(row['tot_suplr_srvcs']) if row.get('tot_suplr_srvcs') else None,
                avg_suplr_sbmtd_chrg=row.get('avg_suplr_sbmtd_chrg') or None,
                avg_suplr_mdcr_alowd_amt=row.get('avg_suplr_mdcr_alowd_amt') or None,
                avg_suplr_mdcr_pymt_amt=row.get('avg_suplr_mdcr_pymt_amt') or None,
                avg_suplr_mdcr_stdzd_amt=row.get('avg_suplr_mdcr_stdzd_amt') or None,
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
        conflict_columns=['npi', 'hcpcs_cd', 'provider_type', '_source_year'],
        update_columns=[
            'tot_suplrs', 'tot_suplr_benes', 'tot_suplr_clms', 'tot_suplr_srvcs',
            'avg_suplr_sbmtd_chrg', 'avg_suplr_mdcr_alowd_amt',
            'avg_suplr_mdcr_pymt_amt', 'avg_suplr_mdcr_stdzd_amt', '_loaded_at',
        ],
    )

    logger.info(f"DME PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
