"""CMS Ordering/Referring Providers PUF loader. Loads to hcs_raw.cms_ordering_providers.

Dataset: "Order and Referring" (UUID c99b5865-1119-4436-bb80-c5af2773ea1f).
This is the CMS PECOS-derived eligibility file — one row per NPI with flags
indicating which Medicare claim types the provider is eligible to order/refer.

Confirmed API columns (GET /data-api/v1/dataset/{uuid}/data?size=2, 2026-03-29):
  NPI → rndrng_npi
  LAST_NAME → rndrng_prvdr_last_org_name
  FIRST_NAME → rndrng_prvdr_first_name
  PARTB → tot_srvcs   (re-used as "Part B eligible" flag)
  DME → rfrd_npi      (re-used as "DME eligible" flag; rfrd_npi will be NULL)
  HHA → (unmapped — home health eligible flag)
  PMD → (unmapped — power mobility device flag)
  HOSPICE → (unmapped — hospice eligible flag)

NOTE: The "Order and Referring" dataset is a single-NPI eligibility list, NOT a
pairwise ordering→referred network dataset.  Fields rfrd_npi, rfrd_prvdr_last_org_name,
rfrd_prvdr_type, tot_benes, tot_mdcr_alowd_amt, tot_mdcr_pymt_amt will always
be NULL for records loaded from this source.
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSOrderingProviderRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    # Actual columns returned by "Order and Referring" API (c99b5865-1119-4436-bb80-c5af2773ea1f):
    # NPI, LAST_NAME, FIRST_NAME, PARTB, DME, HHA, PMD, HOSPICE
    'NPI':        'rndrng_npi',
    'LAST_NAME':  'rndrng_prvdr_last_org_name',
    'FIRST_NAME': 'rndrng_prvdr_first_name',
    # Eligibility flags stored as tot_srvcs (text Y/N) — no numeric totals available.
    # PARTB/DME/HHA/PMD/HOSPICE are Y/N eligibility flags — not mapped to numeric DB fields.
    # HHA, PMD, HOSPICE are additional eligibility flags not mapped to validator fields.
}

TABLE = 'cms_ordering_providers'
SCHEMA = 'hcs_raw'


def load_cms_ordering_providers(filepath: Optional[str] = None, rows: Optional[List[Dict]] = None, source_year: int = 2023, max_records: int = 0, source_hash: Optional[str] = None) -> dict:
    """Load CMS Ordering/Referring Providers PUF data from CSV file."""
    logger.info(f"Loading CMS Ordering Providers (year={source_year})")

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

        df = pd.read_csv(filepath, dtype={'NPI': str}, low_memory=False)

    df = apply_column_mapping(df, COLUMN_MAPPING)
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
                # city, state, zip, type not present in Order and Referring dataset
                rndrng_prvdr_city=None,
                rndrng_prvdr_state_abrvtn=None,
                rndrng_prvdr_zip5=None,
                rndrng_prvdr_type=None,
                # rfrd_npi not present — single-NPI eligibility file, not pairwise
                rfrd_npi=None,
                rfrd_prvdr_last_org_name=None,
                rfrd_prvdr_type=None,
                # tot_srvcs not available — PARTB/DME/HHA are Y/N flags not mapped to integer
                tot_srvcs=None,
                # numeric totals not available in this dataset
                tot_benes=None,
                tot_mdcr_alowd_amt=None,
                tot_mdcr_pymt_amt=None,
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

    # Use rndrng_npi + _source_year as conflict key (rfrd_npi is NULL for this dataset).
    inserted = upsert_records(
        SCHEMA, TABLE, records,
        conflict_columns=['rndrng_npi', '_source_year'],
        update_columns=['_loaded_at'],
    ) if records else 0

    logger.info(f"Ordering Providers load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
