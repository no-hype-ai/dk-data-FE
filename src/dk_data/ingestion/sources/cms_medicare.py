"""CMS Medicare Part B loader — inserts to mol_raw.cms_medicare.

Loads CMS Medicare Part B drug spending records (raw JSONB from the CMS
data API) into mol_raw.cms_medicare. Each row is a drug-year spending
record. Batch insert with executemany for performance.

Target table: mol_raw.cms_medicare
No unique constraint on individual records (each drug×year row is unique
by nature but no expression index is defined). Uses plain INSERT.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)

_BATCH_SIZE = 500


def load_cms_medicare_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load CMS Medicare Part B drug spending records into mol_raw.cms_medicare.

    Each record is stored as a raw JSONB blob. The Bronze model extracts
    typed fields using JSON path operators.

    Records are batch-inserted in groups of 500 for performance. No ON
    CONFLICT handling — each run is treated as a full replacement handled
    at the bronze layer via processed_to_bronze flag lifecycle.

    Args:
        records: List of raw CMS drug-year spending dicts from CMSMedicareFetcher.
        source_hash: Optional content hash; unused but kept for interface consistency.

    Returns:
        Dict with status, records_fetched, records_inserted, errors.
    """
    if not records:
        logger.info("No CMS Medicare records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info(
        "Loading %d CMS Medicare records into mol_raw.cms_medicare", len(records)
    )

    errors: List[str] = []
    inserted = 0

    sql = """
        INSERT INTO mol_raw.cms_medicare (
            request_id, api_endpoint, api_version,
            response_status, response_body, source_id
        )
        VALUES (%s, 'https://data.cms.gov/data-api/v1/dataset', 'v1', 200, %s::JSONB, 'cms_medicare')
    """

    with get_cursor() as cur:
        # Batch insert in chunks for performance
        for batch_start in range(0, len(records), _BATCH_SIZE):
            batch = records[batch_start : batch_start + _BATCH_SIZE]
            batch_values = [
                (f"cms_medicare_{batch_start + i}", json.dumps(rec))
                for i, rec in enumerate(batch)
            ]
            try:
                cur.executemany(sql, batch_values)
                inserted += len(batch)
                logger.debug(
                    "CMS Medicare: inserted batch %d-%d",
                    batch_start, batch_start + len(batch),
                )
            except Exception as exc:
                errors.append(
                    f"batch_start={batch_start} size={len(batch)}: {exc}"
                )
                logger.warning(
                    "CMS Medicare batch insert error at offset=%d: %s",
                    batch_start, exc,
                )

    logger.info(
        "CMS Medicare load complete: %d inserted, %d errors",
        inserted, len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
