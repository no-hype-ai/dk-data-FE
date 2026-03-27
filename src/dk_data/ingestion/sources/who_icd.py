"""WHO ICD Data Loader.

Feature: 015-assessment-dashboard-integration

Loads WHO ICD API responses into mol_raw.who_icd using the standard
JSONB envelope schema (migration 075_pdb_who_raw_tables.sql).

Each record from WHOICDFetcher is one API response object for a single
ICD code. The entire response dict is stored as response_body JSONB.

Target table: mol_raw.who_icd (JSONB envelope — see migration 075)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

BATCH_SIZE = 200


def load_who_icd_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load WHO ICD API response records into mol_raw.who_icd.

    Uses the JSONB envelope pattern: each record is stored verbatim as
    response_body. The icd_code is extracted from the record for the
    request_id to enable deduplication via response_body_hash.

    Args:
        records: List of API response dicts from WHOICDFetcher.fetch().
                 Each dict must contain a 'code' key (ICD code string).
        source_hash: Optional overall content hash for the fetch run.
        source_file: Optional source identifier string.
        batch_size: Number of records per commit.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.info("No WHO ICD records to load")
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info("Loading %d WHO ICD records into mol_raw.who_icd", len(records))

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, record in enumerate(records):
                try:
                    icd_code = (
                        record.get("code")
                        or record.get("stemCode")
                        or f"unknown_{idx}"
                    )
                    response_body_str = json.dumps(record, ensure_ascii=False)
                    body_hash = hashlib.sha256(
                        response_body_str.encode()
                    ).hexdigest()

                    # request_id encodes icd_code for traceability
                    request_id = f"who_icd:{icd_code}"

                    cur.execute(
                        """
                        INSERT INTO mol_raw.who_icd (
                            request_id,
                            request_timestamp,
                            api_endpoint,
                            api_version,
                            request_params,
                            response_status,
                            response_body,
                            response_body_hash,
                            processed_to_bronze,
                            source_id
                        ) VALUES (
                            %s,
                            NOW(),
                            %s,
                            %s,
                            %s,
                            200,
                            %s::JSONB,
                            %s,
                            FALSE,
                            'who_icd'
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            request_id,
                            source_file or "who_icd_api",
                            "v2",
                            json.dumps({"code": icd_code}),
                            response_body_str,
                            body_hash,
                        ),
                    )
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()
                        logger.debug(
                            "Committed batch: %d records so far", records_inserted
                        )

                except Exception as e:
                    records_failed += 1
                    errors.append(
                        {
                            "index": idx,
                            "code": record.get("code"),
                            "error": str(e),
                        }
                    )
                    if records_failed <= 10:
                        logger.error(
                            "Error at index %d (code=%s): %s",
                            idx,
                            record.get("code"),
                            e,
                        )

            conn.commit()

    logger.info(
        "WHO ICD load complete: %d inserted, %d failed",
        records_inserted,
        records_failed,
    )

    return {
        "status": "success" if records_failed == 0 else "partial",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10],
    }
