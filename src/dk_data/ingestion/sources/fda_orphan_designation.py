"""FDA Orphan Drug Designation loader — inserts designation records into mol_raw.fda_orphan_designation.

Source: FDA Office of Orphan Products Development (OOPD) designation database.
Each record is an orphan drug designation dict with designation_number, generic_name, etc.
designation_number is used as the stable request_id.

Target table: mol_raw.fda_orphan_designation (migration 231)
API endpoint: https://www.accessdata.fda.gov/scripts/opdlisting/oopd/listResult.cfm
Feature: 006-claims-engine-data-gaps
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "fda_orphan_designation"
BATCH_SIZE = 500

_SQL = """
    INSERT INTO mol_raw.fda_orphan_designation (
        request_id,
        api_endpoint,
        api_version,
        request_params,
        response_status,
        response_body,
        response_body_hash,
        source_id,
        request_timestamp
    ) VALUES (
        %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s, NOW()
    )
    ON CONFLICT (request_id) DO UPDATE SET
        response_body       = EXCLUDED.response_body,
        response_body_hash  = EXCLUDED.response_body_hash,
        ingested_at         = NOW()
    WHERE mol_raw.fda_orphan_designation.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def load_fda_orphan_designation_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load FDA Orphan Drug Designation records into mol_raw.fda_orphan_designation.

    Args:
        records:     List of designation dicts from FDAOrphanDesignationFetcher.
                     Each dict has designation_number, generic_name, trade_name, etc.
        source_hash: Content hash for lineage tracking.
        batch_size:  Commit interval.

    Returns:
        Dict with status, records_fetched, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("FDA Orphan Designation loader: no records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info(
        "Loading %d FDA Orphan Designation records into mol_raw.fda_orphan_designation",
        len(records),
    )

    inserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in enumerate(records):
                designation_number = (
                    row.get("designation_number")
                    or row.get("Designation Number")
                    or f"orphan_row_{idx}"
                )
                request_id = (
                    f"fda_orphan_{str(designation_number).strip().replace('/', '_').replace(' ', '_')}"
                )
                body_json = json.dumps(row, default=str)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()

                try:
                    cur.execute(
                        _SQL,
                        (
                            request_id,
                            _OOPD_URL,
                            "v1",
                            json.dumps({"designation_number": designation_number}),
                            200,
                            body_json,
                            body_hash,
                            SOURCE_ID,
                        ),
                    )
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()

                except Exception as e:
                    failed += 1
                    if len(errors) < 10:
                        errors.append(
                            {
                                "index": idx,
                                "designation_number": designation_number,
                                "error": str(e)[:300],
                            }
                        )
                    logger.error(
                        "FDA Orphan Designation record %s failed: %s",
                        designation_number,
                        e,
                    )

            conn.commit()

    logger.info(
        "FDA Orphan Designation load: %d inserted, %d failed", inserted, failed
    )
    return {
        "status": "success" if failed == 0 else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors,
    }


# Module-level constant needed by the loader
_OOPD_URL = "https://www.accessdata.fda.gov/scripts/opdlisting/oopd/listResult.cfm"
