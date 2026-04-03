"""CMS Mental Health PUF loader. Loads to hcs_raw.cms_mental_health_puf."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSMentalHealthRecord

logger = logging.getLogger(__name__)

# Canonical CMS column names → internal snake_case names.
# Spec fields: Rndrng_NPI, Rndrng_Prvdr_Last_Org_Name, Rndrng_Prvdr_First_Name,
# Rndrng_Prvdr_City, Rndrng_Prvdr_State_Abrvtn, Rndrng_Prvdr_Zip5, Rndrng_Prvdr_Type,
# HCPCS_Cd, HCPCS_Desc, MH_Srvc_Ind, Tot_Benes, Tot_Srvcs, Tot_Mdcr_Alowd_Amt,
# Avg_Mdcr_Alowd_Amt, Avg_Mdcr_Pymt_Amt, Avg_Mdcr_Stdzd_Amt.
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
    'MH_Srvc_Ind':                   'mh_srvc_ind',
    'Tot_Benes':                     'tot_benes',
    'Tot_Srvcs':                     'tot_srvcs',
    'Tot_Mdcr_Alowd_Amt':            'tot_mdcr_alowd_amt',
    'Avg_Mdcr_Alowd_Amt':            'avg_mdcr_alowd_amt',
    'Avg_Mdcr_Pymt_Amt':             'avg_mdcr_pymt_amt',
    'Avg_Mdcr_Stdzd_Amt':            'avg_mdcr_stdzd_amt',
}

TABLE = 'cms_mental_health_puf'
SCHEMA = 'hcs_raw'


def load_cms_mental_health_puf(filepath: Optional[str] = None, rows: Optional[List[Dict]] = None, source_year: int = 2023, max_records: int = 0, source_hash: Optional[str] = None) -> dict:
    """Load CMS Mental Health PUF data from CSV file."""
    logger.info(f"Loading CMS Mental Health PUF (year={source_year})")

    if rows is not None:
        # Streaming mode: rows passed directly from API, no file needed
        normalized = [{k: ('' if v is None else str(v)) for k, v in row.items()} for row in rows]
        df = pd.DataFrame(normalized) if normalized else pd.DataFrame()
        _source_hash = source_hash or f"api_stream_{source_year}"
        source_file = f"api_stream_{source_year}"
    else:
        if filepath is None:
            raise ValueError("Either filepath or rows must be provided")
        source_file = Path(filepath).name
        hash_md5 = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_md5.update(chunk)
        _source_hash = source_hash or hash_md5.hexdigest()

        with get_cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM {SCHEMA}.{TABLE} WHERE _source_hash = %s",
                (_source_hash,)
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
            rec = CMSMentalHealthRecord(
                npi=row.get('npi'),
                provider_last_org_name=row.get('provider_last_org_name'),
                provider_first_name=row.get('provider_first_name'),
                provider_city=row.get('provider_city'),
                provider_state=row.get('provider_state'),
                provider_zip5=row.get('provider_zip5'),
                provider_type=row.get('provider_type'),
                hcpcs_cd=row.get('hcpcs_cd'),
                hcpcs_desc=row.get('hcpcs_desc'),
                mh_srvc_ind=row.get('mh_srvc_ind'),
                tot_benes=int(float(row['tot_benes'])) if pd.notna(row.get('tot_benes')) else None,
                tot_srvcs=row.get('tot_srvcs') or None,
                tot_mdcr_alowd_amt=row.get('tot_mdcr_alowd_amt') or None,
                avg_mdcr_alowd_amt=row.get('avg_mdcr_alowd_amt') or None,
                avg_mdcr_pymt_amt=row.get('avg_mdcr_pymt_amt') or None,
                avg_mdcr_stdzd_amt=row.get('avg_mdcr_stdzd_amt') or None,
                _source_year=source_year,
            )
            d = rec.model_dump(by_alias=True)
            d['_source_hash'] = _source_hash
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

    logger.info(f"Mental Health PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
