"""CMS Part D Opioid Prescriber PUF loader. Loads to hcs_raw.cms_opioid_puf.

Dataset: Medicare Part D Prescribers - by Provider and Drug
UUID: 9552739e-3d05-4c1b-8eff-ecabf391e2e5

Previous UUID (94d00f36-73ce-4520-9b3f-83cd3cded25c) was wrong — it pointed to
"Medicare Part D Opioid Prescribing Rates - by Geography" (state/county-level
geographic variation), not the prescriber+drug-level dataset needed here.

Confirmed API columns (GET /data-api/v1/dataset/{uuid}/data?size=2, 2026-03-29):
  Prscrbr_NPI, Prscrbr_Last_Org_Name, Prscrbr_First_Name, Prscrbr_City,
  Prscrbr_State_Abrvtn, Prscrbr_State_FIPS, Prscrbr_Type, Prscrbr_Type_Src,
  Brnd_Name, Gnrc_Name, Tot_Clms, Tot_30day_Fills, Tot_Day_Suply, Tot_Drug_Cst,
  Tot_Benes, GE65_Sprsn_Flag, GE65_Tot_Clms, GE65_Tot_30day_Fills,
  GE65_Tot_Drug_Cst, GE65_Tot_Day_Suply, GE65_Bene_Sprsn_Flag, GE65_Tot_Benes

NOTE: The correct prescriber+drug dataset does NOT have Opioid_Drug_Flag,
LA_Opioid_Drug_Flag, Opioid_Clms, Opioid_Benes, LA_Opioid_Clms, LA_Opioid_Benes.
Those fields will always be NULL when loaded from this source.
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSOpioidRecord

logger = logging.getLogger(__name__)

# Confirmed API columns from "Medicare Part D Prescribers - by Provider and Drug"
# UUID: 9552739e-3d05-4c1b-8eff-ecabf391e2e5 (corrected from wrong geographic UUID)
# Opioid_Drug_Flag, LA_Opioid_Drug_Flag, Opioid_Clms/Benes, LA_Opioid_Clms/Benes
# are NOT present in this dataset — those fields will be NULL.
COLUMN_MAPPING = {
    'Prscrbr_NPI':           'prscrbr_npi',
    'Prscrbr_Last_Org_Name': 'prscrbr_last_org_name',
    'Prscrbr_First_Name':    'prscrbr_first_name',
    'Prscrbr_City':          'prscrbr_city',
    'Prscrbr_State_Abrvtn':  'prscrbr_state_abrvtn',
    'Prscrbr_State_FIPS':    'prscrbr_state_fips',
    'Prscrbr_Type':          'prscrbr_type',
    'Prscrbr_Type_Src':      'prscrbr_type_src',
    'Brnd_Name':             'brnd_name',
    'Gnrc_Name':             'gnrc_name',
    'Tot_Clms':              'tot_clms',
    'Tot_30day_Fills':       'tot_30day_fills',
    'Tot_Day_Suply':         'tot_day_suply',
    'Tot_Drug_Cst':          'tot_drug_cst',
    'Tot_Benes':             'tot_benes',
    # Opioid_Drug_Flag, LA_Opioid_Drug_Flag — not in Part D Prescribers by Provider+Drug
    # Opioid_Clms, Opioid_Benes, LA_Opioid_Clms, LA_Opioid_Benes — not in this dataset
}

TABLE = 'cms_opioid_puf'
SCHEMA = 'hcs_raw'


def _safe_int(val) -> int | None:
    """Convert suppressed/blank values to None."""
    if not val or str(val).strip() in ('', '*'):
        return None
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return None


def _safe_decimal(val) -> str | None:
    """Return string for Decimal conversion; None on blank/suppressed."""
    if not val or str(val).strip() in ('', '*'):
        return None
    return str(val).strip()


def load_cms_opioid_puf(filepath: Optional[str] = None, rows: Optional[List[Dict]] = None, source_year: int = 2023, max_records: int = 0, source_hash: Optional[str] = None) -> dict:
    """Load CMS Opioid Prescribing Geographic Variation PUF data from CSV file."""
    logger.info(f"Loading CMS Opioid PUF (year={source_year})")

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
            rec = CMSOpioidRecord(
                prscrbr_npi=row.get('prscrbr_npi'),
                prscrbr_last_org_name=row.get('prscrbr_last_org_name'),
                prscrbr_first_name=row.get('prscrbr_first_name'),
                prscrbr_city=row.get('prscrbr_city'),
                prscrbr_state_abrvtn=row.get('prscrbr_state_abrvtn'),
                prscrbr_state_fips=row.get('prscrbr_state_fips'),
                prscrbr_type=row.get('prscrbr_type'),
                prscrbr_type_src=row.get('prscrbr_type_src'),
                brnd_name=row.get('brnd_name'),
                gnrc_name=row.get('gnrc_name'),
                # Not present in Part D Prescribers by Provider+Drug dataset
                opioid_drug_flag=None,
                la_opioid_drug_flag=None,
                tot_clms=_safe_int(row.get('tot_clms')),
                tot_30day_fills=_safe_decimal(row.get('tot_30day_fills')),
                tot_day_suply=_safe_int(row.get('tot_day_suply')),
                tot_drug_cst=_safe_decimal(row.get('tot_drug_cst')),
                tot_benes=_safe_int(row.get('tot_benes')),
                # Opioid-specific counts not present in this dataset
                opioid_clms=None,
                opioid_benes=None,
                la_opioid_clms=None,
                la_opioid_benes=None,
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
        conflict_columns=['_source_hash', 'prscrbr_npi', 'gnrc_name', '_source_year'],
        update_columns=[
            'tot_clms', 'tot_30day_fills', 'tot_day_suply', 'tot_drug_cst',
            'tot_benes', 'opioid_clms', 'opioid_benes',
            'la_opioid_clms', 'la_opioid_benes', '_loaded_at',
        ],
    )

    logger.info(f"Opioid PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
