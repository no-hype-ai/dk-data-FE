"""CMS Dual Eligible Beneficiary loader. Loads to hcs_raw.cms_dual_eligible.

Accepts records from CMSDualEligibleFetcher.fetch()['records'] — each record is a
dict matching the hcs_raw.cms_dual_eligible schema:
  state_cd, state_name, dual_elgbl_lvl, dual_elgbl_desc,
  tot_benes, ffs_benes, ma_benes, dual_elgbl_full_benes,
  dual_elgbl_prtl_benes, non_dual_benes, lis_benes

Deduplication: ON CONFLICT (state_cd, dual_elgbl_lvl, _source_year) — requires
unique index uq_cms_dual_eligible_key (migration 142).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..utils.database import upsert_records

logger = logging.getLogger(__name__)

TABLE = 'cms_dual_eligible'
SCHEMA = 'hcs_raw'


def load_cms_dual_eligible_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_year: int = 2023,
) -> Dict[str, Any]:
    """Load CMS Dual Eligible records into hcs_raw.cms_dual_eligible.

    Args:
        records: List of dicts from CMSDualEligibleFetcher.fetch()['records'].
        source_hash: Content hash for lineage tracking.
        source_year: Calendar year of the data.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No CMS Dual Eligible records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info(
        "Loading %d CMS Dual Eligible records into %s.%s (year=%d)",
        len(records), SCHEMA, TABLE, source_year,
    )

    loaded_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for rec in records:
        row = dict(rec)
        row['_source_hash'] = source_hash or ""
        row['_source_file'] = f"cms_dual_eligible_{source_year}.xlsx"
        row['_loaded_at'] = loaded_at
        row['_source_year'] = source_year
        rows.append(row)

    inserted = upsert_records(
        SCHEMA, TABLE, rows,
        conflict_columns=['state_cd', 'dual_elgbl_lvl', '_source_year'],
        update_columns=[
            'state_name', 'dual_elgbl_desc', 'tot_benes', 'ffs_benes', 'ma_benes',
            'dual_elgbl_full_benes', 'dual_elgbl_prtl_benes',
            'non_dual_benes', 'lis_benes', '_loaded_at',
        ],
    )

    logger.info("CMS Dual Eligible load complete: %d records inserted/updated", inserted)
    return {
        "status": "success",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": [],
    }
