"""CMS Medicare Enrollment PUF loader. Loads to hcs_raw.cms_enrollment_puf.

Dataset: Medicare Monthly Enrollment
UUID: d7fabe1e-d19b-4333-9eff-e80e0643f2fd

Confirmed API columns (GET /data-api/v1/dataset/{uuid}/data?size=2, 2026-03-29):
  YEAR, MONTH, BENE_GEO_LVL, BENE_STATE_ABRVTN, BENE_STATE_DESC,
  BENE_COUNTY_DESC, BENE_FIPS_CD, TOT_BENES, ORGNL_MDCR_BENES,
  MA_AND_OTH_BENES, AGED_TOT_BENES, AGED_ESRD_BENES, AGED_NO_ESRD_BENES,
  DSBLD_TOT_BENES, DSBLD_ESRD_AND_ESRD_ONLY_BENES, DSBLD_NO_ESRD_BENES,
  MALE_TOT_BENES, FEMALE_TOT_BENES, WHITE_TOT_BENES, BLACK_TOT_BENES,
  API_TOT_BENES, HSPNC_TOT_BENES, NATIND_TOT_BENES, OTHR_TOT_BENES,
  AGE_LT_25_BENES, AGE_25_TO_44_BENES, ..., AGE_GT_94_BENES,
  DUAL_TOT_BENES, FULL_DUAL_TOT_BENES, PART_DUAL_TOT_BENES,
  NODUAL_TOT_BENES, QMB_ONLY_BENES, ... (Part D enrollment columns)

NOTE: API uses ALL_CAPS names. Prior mapping used Sentence_Case names that
do not match the API.  Field mapping to CMSEnrollmentRecord:
  BENE_STATE_ABRVTN → state_cd
  BENE_FIPS_CD      → county_cd
  BENE_COUNTY_DESC  → county_desc
  BENE_GEO_LVL      → bene_demo_lvl
  BENE_STATE_DESC   → bene_demo_desc
  MONTH             → bene_age_lvl  (re-used for month discriminator)
  TOT_BENES         → tot_benes
  ORGNL_MDCR_BENES  → orgnl_mdcr_benes
  MA_AND_OTH_BENES  → ma_benes
  DSBLD_TOT_BENES   → dsbl_benes
  AGED_ESRD_BENES   → esrd_benes
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict

import pandas as pd
from pydantic import ValidationError

from ..utils.database import apply_column_mapping, get_cursor, upsert_records
from ..utils.validators import CMSEnrollmentRecord

logger = logging.getLogger(__name__)

COLUMN_MAPPING = {
    # Actual ALL-CAPS API column names → CMSEnrollmentRecord validator fields.
    'BENE_STATE_ABRVTN':    'state_cd',
    'BENE_FIPS_CD':         'county_cd',
    'BENE_COUNTY_DESC':     'county_desc',
    'BENE_GEO_LVL':         'bene_demo_lvl',
    'BENE_STATE_DESC':      'bene_demo_desc',
    # MONTH re-used in bene_age_lvl to preserve monthly grain uniqueness.
    'MONTH':                'bene_age_lvl',
    'TOT_BENES':            'tot_benes',
    'ORGNL_MDCR_BENES':     'orgnl_mdcr_benes',
    'MA_AND_OTH_BENES':     'ma_benes',
    'AGED_ESRD_BENES':      'esrd_benes',
    'DSBLD_TOT_BENES':      'dsbl_benes',
}

TABLE = 'cms_enrollment_puf'
SCHEMA = 'hcs_raw'


def load_cms_enrollment_puf(filepath: Optional[str] = None, rows: Optional[List[Dict]] = None, source_year: int = 2023, max_records: int = 0, source_hash: Optional[str] = None) -> dict:
    """Load CMS Medicare Enrollment PUF data from CSV file."""
    logger.info(f"Loading CMS Enrollment PUF (year={source_year})")

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
            def _safe_int(val):
                """Convert to int, treating CMS suppression codes and non-numeric as None."""
                if not pd.notna(val):
                    return None
                s = str(val).strip()
                if s in ('', '*', '**', '+', '-', 'N/A', '#'):
                    return None
                try:
                    return int(float(s))
                except (ValueError, TypeError):
                    return None

            rec = CMSEnrollmentRecord(
                state_cd=row.get('state_cd'),
                county_cd=row.get('county_cd'),
                county_desc=row.get('county_desc'),
                bene_demo_lvl=row.get('bene_demo_lvl'),
                bene_demo_desc=row.get('bene_demo_desc'),
                bene_age_lvl=row.get('bene_age_lvl'),
                tot_benes=_safe_int(row.get('tot_benes')),
                orgnl_mdcr_benes=_safe_int(row.get('orgnl_mdcr_benes')),
                ma_benes=_safe_int(row.get('ma_benes')),
                esrd_benes=_safe_int(row.get('esrd_benes')),
                dsbl_benes=_safe_int(row.get('dsbl_benes')),
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
        # state_cd=BENE_STATE_ABRVTN, county_cd=BENE_FIPS_CD,
        # bene_demo_lvl=BENE_GEO_LVL, bene_age_lvl=MONTH
        conflict_columns=['state_cd', 'county_cd', 'bene_demo_lvl', 'bene_age_lvl', '_source_year'],
        update_columns=['tot_benes', 'orgnl_mdcr_benes', 'ma_benes', 'esrd_benes',
                        'dsbl_benes', '_loaded_at'],
    )

    logger.info(f"Enrollment PUF load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
