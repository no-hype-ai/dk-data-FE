"""USPTO CI Source Loader.

Feature: 011-datasource-integration
Task: T055-T057 — USPTO PatentsView CI source integration

Loads USPTO patent records into mol_raw.uspto_ci.
Stores full raw response as JSONB.
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_NAME = 'uspto_ci'
TABLE = 'mol_raw.uspto_ci'
API_ENDPOINT = 'patentsview'


def load_uspto_ci_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load USPTO CI patent records into mol_raw.uspto_ci. Stores full raw response as JSONB."""
    if not records:
        return {"status": "success", "records_inserted": 0, "records_failed": 0}

    logger.info(f"Loading {len(records)} {SOURCE_NAME} records")
    inserted = 0
    failed = 0
    errors = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    response_body = json.dumps(raw_record, default=str)
                    response_hash = hashlib.sha256(response_body.encode()).hexdigest()
                    request_id = raw_record.get('patent_id', f'uspto_ci_{idx}')

                    cur.execute("""
                        INSERT INTO mol_raw.uspto_ci (
                            request_id, api_endpoint,
                            response_status, response_body, response_body_hash,
                            source_id
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (response_body_hash)
                        WHERE response_body_hash IS NOT NULL
                        DO NOTHING
                    """, (
                        str(request_id), API_ENDPOINT,
                        200, response_body, response_hash,
                        SOURCE_NAME,
                    ))
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()
                except Exception as e:
                    failed += 1
                    if len(errors) < 10:
                        errors.append({"index": idx, "error": str(e)[:200]})
                    logger.error(f"{SOURCE_NAME} record {idx} failed: {e}")

            conn.commit()

    logger.info(f"{SOURCE_NAME} load: {inserted} inserted, {failed} failed")
    return {
        "status": "success" if failed == 0 else "partial",
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
