"""CMS Hospice Provider PUF loader. Loads to hcs_raw.cms_hospice_puf."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSHospiceRecord

logger = logging.getLogger(__name__)

# CMS Hospice PUF column names -> internal snake_case names.
# Confirmed API columns (UUID 4e73f1b5, 2026-03-29):
#   YEAR, YEAR_TYPE, SMRY_CTGRY, PRVDR_ID, PRVDR_NAME, STATE, plus spending columns.
# The API uses ALL-CAPS provider fields; mixed-case variants kept for file import fallback.
COLUMN_MAPPING = {
    # ALL-CAPS provider fields (confirmed API format for UUID 4e73f1b5)
    'PRVDR_ID':                 'provider_id',
    'PRVDR_NAME':               'provider_name',
    'PRVDR_CITY':               'provider_city',
    'STATE':                    'provider_state',
    'PRVDR_STATE':              'provider_state',
    'PRVDR_ZIP':                'provider_zip5',
    'SMRY_CTGRY':               'hspce_cd',
    'SRVC_CTGRY':               'hspce_desc',
    # Alternate/mixed-case provider fields (some API versions or file downloads)
    'Rndrng_Prvdr_Id':          'provider_id',
    'Rndrng_Prvdr_Name':        'provider_name',
    'Rndrng_Prvdr_City':        'provider_city',
    'Rndrng_Prvdr_State_Abrvtn':'provider_state',
    'Rndrng_Prvdr_Zip5':        'provider_zip5',
    # Hospice service category columns
    'HSPCE_CD':                 'hspce_cd',
    'HSPCE_DESC':               'hspce_desc',
    # Utilization and spending columns (ALL-CAPS and mixed-case variants)
    'BENE_DSTNCT_CNT':          'tot_benes',
    'BENE_CNT':                 'tot_benes',
    'Tot_Benes':                'tot_benes',
    'TOT_ALOWD_AMT':            'tot_mdcr_alowd_amt',
    'Tot_Mdcr_Alowd_Amt':       'tot_mdcr_alowd_amt',
    'Tot_Mdcr_Pymt_Amt':        'tot_mdcr_pymt_amt',
    'Avg_Mdcr_Pymt_Amt':        'avg_mdcr_pymt_amt',
    'AVG_MDCR_PYMT_AMT':        'avg_mdcr_pymt_amt',
    'Avg_Age':                  'avg_age',
    'BENE_AVG_AGE':             'avg_age',
}

TABLE = 'cms_hospice_puf'
SCHEMA = 'hcs_raw'


def load_cms_hospice_puf(filepath: Optional[str] = None, rows: Optional[List[Dict]] = None, source_year: int = 2023, max_records: int = 0, source_hash: Optional[str] = None) -> dict:
    """Load CMS Hospice Provider PUF data from CSV file."""
    logger.info(f"Loading CMS Hospice PUF (year={source_year})")

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
            rec = CMSHospiceRecord(
                provider_id=row.get('provider_id'),
                provider_name=row.get('provider_name'),
                provider_city=row.get('provider_city'),
                provider_state=row.get('provider_state'),
                provider_zip5=row.get('provider_zip5'),
                hspce_cd=row.get('hspce_cd'),
                hspce_desc=row.get('hspce_desc'),
                tot_benes=(lambda v: int(float(str(v).strip())) if pd.notna(v) and str(v).strip() not in ('', '*', '**', '+', '-', 'N/A', '#') else None)(row.get('tot_benes')),
                tot_mdcr_alowd_amt=row.get('tot_mdcr_alowd_amt') or None,
                tot_mdcr_pymt_amt=row.get('tot_mdcr_pymt_amt') or None,
                avg_mdcr_pymt_amt=row.get('avg_mdcr_pymt_amt') or None,
                avg_age=row.get('avg_age') or None,
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
        conflict_columns=['provider_id', 'hspce_cd', '_source_year'],
        update_columns=[
            'tot_benes', 'tot_mdcr_alowd_amt', 'tot_mdcr_pymt_amt',
            'avg_mdcr_pymt_amt', 'avg_age', '_loaded_at',
        ],
    )

    logger.info(f"Hospice PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
