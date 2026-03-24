"""Source loader for CMS Hospital Affiliation data."""
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_NAME = 'cms_hospital_affiliation'
TABLE = 'hcs_raw.cms_hospital_affiliation'
API_ENDPOINT = 'cms_hospital_affiliation'


def load_cms_hospital_affiliation_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS Hospital Affiliation records into hcs_raw.cms_hospital_affiliation as JSONB."""
    if not records:
        return {"status": "success", "records_inserted": 0, "records_failed": 0}

    logger.info("Loading %d %s records", len(records), SOURCE_NAME)
    inserted = 0
    failed = 0
    errors = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    response_body = json.dumps(raw_record, default=str)
                    response_hash = hashlib.sha256(response_body.encode()).hexdigest()
                    request_id = str(raw_record.get('npi', f'{SOURCE_NAME}_{idx}'))

                    cur.execute("""
                        INSERT INTO hcs_raw.cms_hospital_affiliation (
                            request_id, api_endpoint,
                            response_status, response_body, response_body_hash,
                            source_id
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (response_body_hash)
                        WHERE response_body_hash IS NOT NULL
                        DO NOTHING
                    """, (
                        request_id, API_ENDPOINT,
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
                    logger.error("%s record %d failed: %s", SOURCE_NAME, idx, e)

            conn.commit()

    logger.info("%s load: %d inserted, %d failed", SOURCE_NAME, inserted, failed)
    return {
        "status": "success" if failed == 0 else "partial",
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
