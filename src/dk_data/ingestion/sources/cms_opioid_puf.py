"""CMS Opioid Prescribing Geographic Variation PUF loader. Loads to hcs_raw.cms_opioid_puf."""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSOpioidRecord

logger = logging.getLogger(__name__)

# Canonical CMS column names → internal snake_case names.
# Spec fields: Prscrbr_NPI, Prscrbr_Last_Org_Name, Prscrbr_First_Name,
# Prscrbr_City, Prscrbr_State_Abrvtn, Prscrbr_State_FIPS, Prscrbr_Type,
# Prscrbr_Type_Src, Brnd_Name, Gnrc_Name, Opioid_Drug_Flag, LA_Opioid_Drug_Flag,
# Tot_Clms, Tot_30day_Fills, Tot_Day_Suply, Tot_Drug_Cst, Tot_Benes,
# Opioid_Clms, Opioid_Benes, LA_Opioid_Clms, LA_Opioid_Benes.
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
    'Opioid_Drug_Flag':      'opioid_drug_flag',
    'LA_Opioid_Drug_Flag':   'la_opioid_drug_flag',
    'Tot_Clms':              'tot_clms',
    'Tot_30day_Fills':       'tot_30day_fills',
    'Tot_Day_Suply':         'tot_day_suply',
    'Tot_Drug_Cst':          'tot_drug_cst',
    'Tot_Benes':             'tot_benes',
    'Opioid_Clms':           'opioid_clms',
    'Opioid_Benes':          'opioid_benes',
    'LA_Opioid_Clms':        'la_opioid_clms',
    'LA_Opioid_Benes':       'la_opioid_benes',
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


def load_cms_opioid_puf(filepath: str, source_year: int = 2023, max_records: int = 0) -> dict:
    """Load CMS Opioid Prescribing Geographic Variation PUF data from CSV file."""
    logger.info(f"Loading CMS Opioid PUF from {filepath} (year={source_year})")

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
                opioid_drug_flag=row.get('opioid_drug_flag'),
                la_opioid_drug_flag=row.get('la_opioid_drug_flag'),
                tot_clms=_safe_int(row.get('tot_clms')),
                tot_30day_fills=_safe_decimal(row.get('tot_30day_fills')),
                tot_day_suply=_safe_int(row.get('tot_day_suply')),
                tot_drug_cst=_safe_decimal(row.get('tot_drug_cst')),
                tot_benes=_safe_int(row.get('tot_benes')),
                opioid_clms=_safe_int(row.get('opioid_clms')),
                opioid_benes=_safe_int(row.get('opioid_benes')),
                la_opioid_clms=_safe_int(row.get('la_opioid_clms')),
                la_opioid_benes=_safe_int(row.get('la_opioid_benes')),
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
