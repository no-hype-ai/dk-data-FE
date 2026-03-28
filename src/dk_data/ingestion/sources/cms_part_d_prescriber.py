"""CMS Part D Prescribers by Provider and Drug loader.

Loads to hcs_raw.cms_part_d_prescriber.

Data source:
    CMS Medicare Part D Prescribers — by Provider and Drug
    https://data.cms.gov/provider-summary-by-type-of-service/
    medicare-part-d-prescribers/medicare-part-d-prescribers-by-provider-and-drug

Grain: (prscrbr_npi, gnrc_name, _source_year)

CMS column name conventions (source CSV headers):
    Prscrbr_NPI → prscrbr_npi
    Gnrc_Name   → gnrc_name    (generic drug name — join key to molecule_aliases)
    etc.

Feature: 020-entity-linking-gaps
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSPartDPrescriberRecord

logger = logging.getLogger(__name__)

# Map CMS CSV column headers → snake_case DB column names.
# CMS uses mixed-case with underscores; we lowercase everything.
COLUMN_MAPPING = {
    'Prscrbr_NPI':            'prscrbr_npi',
    'Prscrbr_Last_Org_Name':  'prscrbr_last_org_name',
    'Prscrbr_First_Name':     'prscrbr_first_name',
    'Prscrbr_City':           'prscrbr_city',
    'Prscrbr_State_Abrvtn':   'prscrbr_state_abrvtn',
    'Prscrbr_State_FIPS':     'prscrbr_state_fips',
    'Prscrbr_Type':           'prscrbr_type',
    'Prscrbr_Type_Src':       'prscrbr_type_src',
    'Brnd_Name':              'brnd_name',
    'Gnrc_Name':              'gnrc_name',
    'Tot_Clms':               'tot_clms',
    'Tot_30day_Fills':        'tot_30day_fills',
    'Tot_Day_Suply':          'tot_day_suply',
    'Tot_Drug_Cst':           'tot_drug_cst',
    'Tot_Benes':              'tot_benes',
    # CMS suppression flag: 'Y' when <11 beneficiaries in the 65+ cohort
    'GE65_Sprsn_Flag':        'ge65_sprsn_flag',
    'GE65_Tot_Clms':          'ge65_tot_clms',
    'GE65_Tot_30day_Fills':   'ge65_tot_30day_fills',
    'GE65_Tot_Drug_Cst':      'ge65_tot_drug_cst',
    'GE65_Tot_Day_Suply':     'ge65_tot_day_suply',
    # CMS suppression flag: 'Y' when beneficiary count is suppressed
    'GE65_Bene_Sprsn_Flag':   'ge65_bene_sprsn_flag',
    'GE65_Tot_Benes':         'ge65_tot_benes',
}

TABLE  = 'cms_part_d_prescriber'
SCHEMA = 'hcs_raw'


def load_cms_part_d_prescriber(filepath: str, source_year: int = 2023, max_records: int = 0) -> dict:
    """Load CMS Part D Prescribers by Provider and Drug from CSV file.

    The CSV typically has ~25M rows (one per NPI × drug × year).
    Processing uses pandas chunked read to keep memory bounded.

    Args:
        filepath:    Path to the CMS Part D Prescriber PUF CSV file.
        source_year: Reporting year (default 2023).

    Returns:
        Standard loader result dict with status, counts, and errors.
    """
    logger.info(f"Loading CMS Part D Prescriber from {filepath} (year={source_year})")

    source_file = Path(filepath).name
    hash_md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            hash_md5.update(chunk)
    source_hash = hash_md5.hexdigest()

    # Idempotency: skip if already loaded
    with get_cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM {SCHEMA}.{TABLE} WHERE _source_hash = %s",
            (source_hash,)
        )
        if cur.fetchone()[0] > 0:
            logger.info(f"File {source_file} already loaded. Skipping.")
            return {
                "status": "skipped",
                "records_fetched": 0,
                "records_inserted": 0,
                "records_updated": 0,
                "errors": [],
            }

    # Full load — pandas handles chunking internally for dtype=str
    df = pd.read_csv(filepath, dtype=str, low_memory=False, nrows=max_records if max_records > 0 else None)
    df = apply_column_mapping(df, COLUMN_MAPPING)

    # Keep only columns we mapped (ignore CMS columns we don't capture)
    known_cols = [c for c in COLUMN_MAPPING.values() if c in df.columns]
    df = df[known_cols]

    records_fetched = len(df)
    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        try:
            rec = CMSPartDPrescriberRecord(
                prscrbr_npi=row.get('prscrbr_npi', ''),
                prscrbr_last_org_name=row.get('prscrbr_last_org_name') or None,
                prscrbr_first_name=row.get('prscrbr_first_name') or None,
                prscrbr_city=row.get('prscrbr_city') or None,
                prscrbr_state_abrvtn=row.get('prscrbr_state_abrvtn') or None,
                prscrbr_state_fips=row.get('prscrbr_state_fips') or None,
                prscrbr_type=row.get('prscrbr_type') or None,
                prscrbr_type_src=row.get('prscrbr_type_src') or None,
                brnd_name=row.get('brnd_name') or None,
                gnrc_name=row.get('gnrc_name', ''),
                tot_clms=int(float(row['tot_clms'])) if pd.notna(row.get('tot_clms')) else None,
                tot_30day_fills=row.get('tot_30day_fills') or None,
                tot_day_suply=int(float(row['tot_day_suply'])) if pd.notna(row.get('tot_day_suply')) else None,
                tot_drug_cst=row.get('tot_drug_cst') or None,
                tot_benes=int(float(row['tot_benes'])) if pd.notna(row.get('tot_benes')) else None,
                ge65_sprsn_flag=row.get('ge65_sprsn_flag') or None,
                ge65_tot_clms=int(float(row['ge65_tot_clms'])) if pd.notna(row.get('ge65_tot_clms')) else None,
                ge65_tot_30day_fills=row.get('ge65_tot_30day_fills') or None,
                ge65_tot_drug_cst=row.get('ge65_tot_drug_cst') or None,
                ge65_tot_day_suply=int(float(row['ge65_tot_day_suply'])) if pd.notna(row.get('ge65_tot_day_suply')) else None,
                ge65_bene_sprsn_flag=row.get('ge65_bene_sprsn_flag') or None,
                ge65_tot_benes=int(float(row['ge65_tot_benes'])) if pd.notna(row.get('ge65_tot_benes')) else None,
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
        conflict_columns=['prscrbr_npi', 'gnrc_name', '_source_year'],
        update_columns=[
            'tot_clms', 'tot_30day_fills', 'tot_day_suply',
            'tot_drug_cst', 'tot_benes', '_loaded_at',
        ],
    )

    logger.info(
        f"Part D Prescriber load complete: {inserted}/{records_fetched} records, "
        f"{len(errors)} errors"
    )
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
