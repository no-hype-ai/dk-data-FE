"""CMS Dual Eligible Beneficiary loader. Loads to hcs_raw.cms_dual_eligible.

Accepts records from CMSDualEligibleFetcher.fetch()['records'] — each record is a
dict matching the hcs_raw.cms_dual_eligible schema:
  state_cd, state_name, dual_elgbl_lvl, dual_elgbl_desc,
  tot_benes, ffs_benes, ma_benes, dual_elgbl_full_benes,
  dual_elgbl_prtl_benes, non_dual_benes, lis_benes

Deduplication: ON CONFLICT (state_cd, dual_elgbl_lvl, _source_year) — requires
unique index uq_cms_dual_eligible_key (migration 142).
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from ..utils.database import upsert_records, get_cursor

logger = logging.getLogger(__name__)

TABLE = 'cms_dual_eligible'
SCHEMA = 'hcs_raw'

COLUMN_MAPPING = {
    'State_Cd': 'state_cd',
    'STATE_CD': 'state_cd',
    'State_Name': 'state_name',
    'STATE_NAME': 'state_name',
    'Dual_Elgbl_Lvl': 'dual_elgbl_lvl',
    'DUAL_ELGBL_LVL': 'dual_elgbl_lvl',
    'Dual_Elgbl_Desc': 'dual_elgbl_desc',
    'DUAL_ELGBL_DESC': 'dual_elgbl_desc',
    'Tot_Benes': 'tot_benes',
    'TOT_BENES': 'tot_benes',
    'FFS_Benes': 'ffs_benes',
    'FFS_BENES': 'ffs_benes',
    'MA_Benes': 'ma_benes',
    'MA_BENES': 'ma_benes',
    'Dual_Elgbl_Full_Benes': 'dual_elgbl_full_benes',
    'DUAL_ELGBL_FULL_BENES': 'dual_elgbl_full_benes',
    'Dual_Elgbl_Prtl_Benes': 'dual_elgbl_prtl_benes',
    'DUAL_ELGBL_PRTL_BENES': 'dual_elgbl_prtl_benes',
    'Non_Dual_Benes': 'non_dual_benes',
    'NON_DUAL_BENES': 'non_dual_benes',
    'LIS_Benes': 'lis_benes',
    'LIS_BENES': 'lis_benes',
}


def _safe_int(val) -> int | None:
    """Convert suppressed/blank values to None."""
    if val is None:
        return None
    s = str(val).strip()
    if s in ('', '*', '**', '+', '-', 'N/A', '#'):
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def load_cms_dual_eligible(filepath: Optional[str] = None, rows: Optional[List[Dict]] = None, source_year: int = 2023, max_records: int = 0, source_hash: Optional[str] = None) -> dict:
    """Load CMS Dual Eligible data from CSV file or streaming rows.

    Args:
        filepath: Path to CSV file.
        rows: List of dicts from API streaming mode.
        source_hash: Content hash for lineage tracking.
        source_year: Calendar year of the data.
        max_records: Max records to load (0 = unlimited).

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    logger.info(f"Loading CMS Dual Eligible (year={source_year})")

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

    # Apply column mapping for CSV/API column names
    from ..utils.database import apply_column_mapping
    df = apply_column_mapping(df, COLUMN_MAPPING)
    records_fetched = len(df)

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row_data in df.iterrows():
        try:
            record = {
                'state_cd': row_data.get('state_cd'),
                'state_name': row_data.get('state_name'),
                'dual_elgbl_lvl': row_data.get('dual_elgbl_lvl'),
                'dual_elgbl_desc': row_data.get('dual_elgbl_desc'),
                'tot_benes': _safe_int(row_data.get('tot_benes')),
                'ffs_benes': _safe_int(row_data.get('ffs_benes')),
                'ma_benes': _safe_int(row_data.get('ma_benes')),
                'dual_elgbl_full_benes': _safe_int(row_data.get('dual_elgbl_full_benes')),
                'dual_elgbl_prtl_benes': _safe_int(row_data.get('dual_elgbl_prtl_benes')),
                'non_dual_benes': _safe_int(row_data.get('non_dual_benes')),
                'lis_benes': _safe_int(row_data.get('lis_benes')),
                '_source_hash': _source_hash,
                '_source_file': source_file,
                '_loaded_at': loaded_at,
                '_source_year': source_year,
            }
            records.append(record)
        except Exception as e:
            errors.append(f"Row {idx}: {e}")

    inserted = upsert_records(
        SCHEMA, TABLE, records,
        conflict_columns=['state_cd', 'dual_elgbl_lvl', '_source_year'],
        update_columns=[
            'state_name', 'dual_elgbl_desc', 'tot_benes', 'ffs_benes', 'ma_benes',
            'dual_elgbl_full_benes', 'dual_elgbl_prtl_benes',
            'non_dual_benes', 'lis_benes', '_loaded_at',
        ],
    ) if records else 0

    logger.info(f"CMS Dual Eligible load complete: {inserted} records processed, {len(errors)} errors")
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }


def load_cms_dual_eligible_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_year: int = 2023,
) -> Dict[str, Any]:
    """Load CMS Dual Eligible records into hcs_raw.cms_dual_eligible.

    Legacy wrapper — delegates to load_cms_dual_eligible(rows=...).

    Args:
        records: List of dicts from CMSDualEligibleFetcher.fetch()['records'].
        source_hash: Content hash for lineage tracking.
        source_year: Calendar year of the data.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    return load_cms_dual_eligible(rows=records, source_hash=source_hash, source_year=source_year)
