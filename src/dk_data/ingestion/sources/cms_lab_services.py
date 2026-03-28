"""CMS Lab Services PUF loader. Loads to hcs_raw.cms_lab_services."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import get_cursor, upsert_records
from ..utils.validators import CMSLabServicesRecord

logger = logging.getLogger(__name__)

# Exact CMS Medicare Lab Services PUF column names -> internal snake_case names
# Provider-level PUF: NPI × HCPCS × year
COLUMN_MAPPING = {
    'Rndrng_NPI':               'npi',
    'Rndrng_Prvdr_Last_Org_Name':'provider_last_org_name',
    'Rndrng_Prvdr_City':        'provider_city',
    'Rndrng_Prvdr_State_Abrvtn':'provider_state',
    'Rndrng_Prvdr_Zip5':        'provider_zip5',
    'Rndrng_Prvdr_Type':        'provider_type',
    'HCPCS_Cd':                 'hcpcs_cd',
    'HCPCS_Desc':               'hcpcs_desc',
    'Tot_Benes':                'tot_benes',
    'Tot_Srvcs':                'tot_srvcs',
    'Tot_Mdcr_Alowd_Amt':       'tot_mdcr_alowd_amt',
    'Avg_Mdcr_Alowd_Amt':       'avg_mdcr_alowd_amt',
    'Avg_Mdcr_Pymt_Amt':        'avg_mdcr_pymt_amt',
    'Avg_Mdcr_Stdzd_Amt':       'avg_mdcr_stdzd_amt',
}

TABLE = 'cms_lab_services'
SCHEMA = 'hcs_raw'


def load_cms_lab_services(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Lab Services PUF data from CSV file."""
    logger.info(f"Loading CMS Lab Services from {filepath} (year={source_year})")

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
            rec = CMSLabServicesRecord(
                npi=row.get('npi'),
                provider_last_org_name=row.get('provider_last_org_name'),
                provider_city=row.get('provider_city'),
                provider_state=row.get('provider_state'),
                provider_zip5=row.get('provider_zip5'),
                provider_type=row.get('provider_type'),
                hcpcs_cd=row.get('hcpcs_cd'),
                hcpcs_desc=row.get('hcpcs_desc'),
                tot_benes=int(float(row['tot_benes'])) if pd.notna(row.get('tot_benes')) else None,
                tot_srvcs=int(float(row['tot_srvcs'])) if pd.notna(row.get('tot_srvcs')) else None,
                tot_mdcr_alowd_amt=row.get('tot_mdcr_alowd_amt') or None,
                avg_mdcr_alowd_amt=row.get('avg_mdcr_alowd_amt') or None,
                avg_mdcr_pymt_amt=row.get('avg_mdcr_pymt_amt') or None,
                avg_mdcr_stdzd_amt=row.get('avg_mdcr_stdzd_amt') or None,
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
        conflict_columns=['npi', 'hcpcs_cd', '_source_year'],
        update_columns=[
            'tot_benes', 'tot_srvcs', 'tot_mdcr_alowd_amt',
            'avg_mdcr_alowd_amt', 'avg_mdcr_pymt_amt', 'avg_mdcr_stdzd_amt', '_loaded_at',
        ],
    )

    logger.info(f"Lab Services load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
