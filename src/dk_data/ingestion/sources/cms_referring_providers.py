"""CMS Referring Providers PUF loader. Loads to hcs_raw.cms_referring_providers.

Dataset: "Order and Referring" (UUID c99b5865-1119-4436-bb80-c5af2773ea1f).
This is the same PECOS-derived eligibility file as cms_ordering_providers — a
single-NPI eligibility list, NOT a pairwise ordering→referred network dataset.

Confirmed API columns (GET /data-api/v1/dataset/{uuid}/data?size=2, 2026-03-29):
  NPI, LAST_NAME, FIRST_NAME, PARTB, DME, HHA, PMD, HOSPICE

NOTE: rfrd_npi is always NULL for records from this source (no pairwise data).
The DB unique constraint (rndrng_npi, rfrd_npi, _source_year) cannot be used for
ON CONFLICT because NULL ≠ NULL in PostgreSQL unique indexes. Use INSERT ... ON
CONFLICT DO NOTHING instead.
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSReferringProviderRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    # "Order and Referring" CMS dataset (c99b5865...) uses bare NPI/LAST_NAME/FIRST_NAME
    'NPI': 'rndrng_npi',
    'LAST_NAME': 'rndrng_prvdr_last_org_name',
    'FIRST_NAME': 'rndrng_prvdr_first_name',
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
    'Avg_Suplr_Mdcr_Alowd_Amt': 'tot_mdcr_alowd_amt',
    'Tot_Mdcr_Pymt_Amt': 'tot_mdcr_pymt_amt',
    'Avg_Suplr_Mdcr_Pymt_Amt': 'tot_mdcr_pymt_amt',
}

TABLE = 'cms_referring_providers'
SCHEMA = 'hcs_raw'


def load_cms_referring_providers(filepath: Optional[str] = None, rows: Optional[List[Dict]] = None, source_year: int = 2023, max_records: int = 0, source_hash: Optional[str] = None) -> dict:
    """Load CMS Referring Providers PUF data from CSV file."""
    logger.info(f"Loading CMS Referring Providers (year={source_year})")

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

        df = pd.read_csv(filepath, dtype={'NPI': str, 'Rndrng_NPI': str, 'Rfrd_NPI': str,
                                          'Rndrng_Prvdr_Zip5': str}, low_memory=False)

    df = apply_column_mapping(df, COLUMN_MAPPING)
    records_fetched = len(df)

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        try:
            rec = CMSReferringProviderRecord(
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
                tot_benes=(lambda v: int(float(str(v).strip())) if pd.notna(v) and str(v).strip() not in ('', '*', '**', '+', '-', 'N/A', '#') else None)(row.get('tot_benes')),
                tot_mdcr_alowd_amt=row.get('tot_mdcr_alowd_amt') or None,
                tot_mdcr_pymt_amt=row.get('tot_mdcr_pymt_amt') or None,
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

    # Use rndrng_npi + _source_year as conflict key (rfrd_npi is NULL for this PECOS dataset).
    inserted = upsert_records(
        SCHEMA, TABLE, records,
        conflict_columns=['rndrng_npi', '_source_year'],
        update_columns=['_loaded_at'],
    ) if records else 0

    logger.info(f"Referring Providers load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
