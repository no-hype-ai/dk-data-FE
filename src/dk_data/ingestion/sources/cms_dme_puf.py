"""CMS Durable Medical Equipment (DME) PUF loader. Loads to hcs_raw.cms_dme_puf."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSDMERecord

logger = logging.getLogger(__name__)

# CMS DME by Supplier and Service column names -> internal snake_case.
# Source dataset: Medicare DME Devices & Supplies - by Supplier and Service
# UUID: 1746a83e-bb65-4300-8e02-21edbab77c6b
# Confirmed API columns (GET /data-api/v1/dataset/{uuid}/data?size=2, 2026-03-29):
#   Suplr_NPI, Suplr_Prvdr_Last_Name_Org, Suplr_Prvdr_First_Name, Suplr_Prvdr_MI,
#   Suplr_Prvdr_Crdntls, Suplr_Prvdr_Ent_Cd, Suplr_Prvdr_St1, Suplr_Prvdr_St2,
#   Suplr_Prvdr_City, Suplr_Prvdr_State_Abrvtn, Suplr_Prvdr_State_FIPS,
#   Suplr_Prvdr_Zip5, Suplr_Prvdr_RUCA_Cat, Suplr_Prvdr_RUCA, Suplr_Prvdr_RUCA_Desc,
#   Suplr_Prvdr_Cntry, Suplr_Prvdr_Spclty_Cd, Suplr_Prvdr_Spclty_Desc,
#   Suplr_Prvdr_Spclty_Srce, RBCS_Lvl, RBCS_Id, RBCS_Desc, HCPCS_Cd, HCPCS_Desc,
#   Suplr_Rentl_Ind, Tot_Suplr_Benes, Tot_Suplr_Clms, Tot_Suplr_Srvcs,
#   Avg_Suplr_Sbmtd_Chrg, Avg_Suplr_Mdcr_Alowd_Amt, Avg_Suplr_Mdcr_Pymt_Amt,
#   Avg_Suplr_Mdcr_Stdzd_Amt
# NOTE: API uses Suplr_Prvdr_Last_Name_Org (not Suplr_Prvdr_Last_Org_Name).
# NOTE: Tot_Suplrs does NOT exist in the API; tot_suplrs field will always be NULL.
COLUMN_MAPPING = {
    'Suplr_NPI':                    'npi',
    'Suplr_Prvdr_Last_Name_Org':    'provider_last_org_name',
    'Suplr_Prvdr_First_Name':       'provider_first_name',
    'Suplr_Prvdr_City':             'provider_city',
    'Suplr_Prvdr_State_Abrvtn':     'provider_state',
    'Suplr_Prvdr_State_FIPS':       'provider_state_fips',
    'Suplr_Prvdr_Zip5':             'provider_zip5',
    'Suplr_Prvdr_RUCA':             'provider_ruca',
    'Suplr_Prvdr_Spclty_Desc':      'provider_type',
    'HCPCS_Cd':                     'hcpcs_cd',
    'HCPCS_Desc':                   'hcpcs_desc',
    'Suplr_Rentl_Ind':              'suplr_rentl_ind',
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


def load_cms_dme_puf(filepath: str, source_year: int = 2023, max_records: int = 0) -> dict:
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

    df = pd.read_csv(filepath, dtype=str, low_memory=False, nrows=max_records if max_records > 0 else None)
    df = apply_column_mapping(df, COLUMN_MAPPING)
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
                tot_suplrs=None,  # Tot_Suplrs not present in CMS DME API dataset
                tot_suplr_benes=int(float(row['tot_suplr_benes'])) if pd.notna(row.get('tot_suplr_benes')) else None,
                tot_suplr_clms=int(float(row['tot_suplr_clms'])) if pd.notna(row.get('tot_suplr_clms')) else None,
                tot_suplr_srvcs=int(float(row['tot_suplr_srvcs'])) if pd.notna(row.get('tot_suplr_srvcs')) else None,
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
            d['_source_year'] = source_year
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
