"""CMS Telehealth Utilization PUF loader. Loads to hcs_raw.cms_telehealth_puf."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSTelehealthRecord

logger = logging.getLogger(__name__)

# Canonical CMS column names → internal snake_case names.
# Source: Medicare Physician & Other Practitioners - by Provider and Service
# (UUID 92396110-2aed-4d63-a6a2-5d6207d46a29).
# CMS has no separate telehealth-only PUF; Place_Of_Srvc='02' marks telehealth
# services and is mapped to th_srvc_ind for downstream filtering.
# Confirmed API columns (GET /data-api/v1/dataset/{uuid}/data?size=2, 2026-03-29):
#   Rndrng_NPI, Rndrng_Prvdr_Last_Org_Name, Rndrng_Prvdr_First_Name,
#   Rndrng_Prvdr_MI, Rndrng_Prvdr_Crdntls, Rndrng_Prvdr_Ent_Cd,
#   Rndrng_Prvdr_St1, Rndrng_Prvdr_St2, Rndrng_Prvdr_City,
#   Rndrng_Prvdr_State_Abrvtn, Rndrng_Prvdr_State_FIPS, Rndrng_Prvdr_Zip5,
#   Rndrng_Prvdr_RUCA, Rndrng_Prvdr_RUCA_Desc, Rndrng_Prvdr_Cntry,
#   Rndrng_Prvdr_Type, Rndrng_Prvdr_Mdcr_Prtcptg_Ind, HCPCS_Cd, HCPCS_Desc,
#   HCPCS_Drug_Ind, Place_Of_Srvc, Tot_Benes, Tot_Srvcs, Tot_Bene_Day_Srvcs,
#   Avg_Sbmtd_Chrg, Avg_Mdcr_Alowd_Amt, Avg_Mdcr_Pymt_Amt, Avg_Mdcr_Stdzd_Amt
COLUMN_MAPPING = {
    'Rndrng_NPI':                    'npi',
    'Rndrng_Prvdr_Last_Org_Name':    'provider_last_org_name',
    'Rndrng_Prvdr_First_Name':       'provider_first_name',
    'Rndrng_Prvdr_City':             'provider_city',
    'Rndrng_Prvdr_State_Abrvtn':     'provider_state',
    'Rndrng_Prvdr_Zip5':             'provider_zip5',
    'Rndrng_Prvdr_Type':             'provider_type',
    'HCPCS_Cd':                      'hcpcs_cd',
    'HCPCS_Desc':                    'hcpcs_desc',
    # Place_Of_Srvc='02' = telehealth; no separate TH_Srvc_Ind column in this dataset.
    'Place_Of_Srvc':                 'th_srvc_ind',
    'Tot_Benes':                     'tot_benes',
    'Tot_Srvcs':                     'tot_srvcs',
    # API does NOT have Tot_Mdcr_Alowd_Amt; the per-service average is Avg_Mdcr_Alowd_Amt.
    'Avg_Mdcr_Alowd_Amt':            'avg_mdcr_alowd_amt',
    'Avg_Mdcr_Pymt_Amt':             'avg_mdcr_pymt_amt',
    'Avg_Mdcr_Stdzd_Amt':            'avg_mdcr_stdzd_amt',
}

TABLE = 'cms_telehealth_puf'
SCHEMA = 'hcs_raw'


def load_cms_telehealth_puf(filepath: str, source_year: int = 2023, max_records: int = 0) -> dict:
    """Load CMS Telehealth Utilization PUF data from CSV file."""
    logger.info(f"Loading CMS Telehealth PUF from {filepath} (year={source_year})")

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
            rec = CMSTelehealthRecord(
                npi=row.get('npi'),
                provider_last_org_name=row.get('provider_last_org_name'),
                provider_first_name=row.get('provider_first_name'),
                provider_city=row.get('provider_city'),
                provider_state=row.get('provider_state'),
                provider_zip5=row.get('provider_zip5'),
                provider_type=row.get('provider_type'),
                hcpcs_cd=row.get('hcpcs_cd'),
                hcpcs_desc=row.get('hcpcs_desc'),
                th_srvc_ind=row.get('th_srvc_ind'),
                tot_benes=int(float(row['tot_benes'])) if pd.notna(row.get('tot_benes')) else None,
                tot_srvcs=row.get('tot_srvcs') or None,
                tot_mdcr_alowd_amt=None,  # not present in this dataset (avg only)
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
            'avg_mdcr_alowd_amt', 'avg_mdcr_pymt_amt', 'avg_mdcr_stdzd_amt',
            '_loaded_at',
        ],
    )

    logger.info(f"Telehealth PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
