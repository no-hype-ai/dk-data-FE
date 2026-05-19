"""FDA NDC loader — inserts product records into mol_raw.fda_ndc.

Source: OpenFDA /drug/ndc endpoint.
Each record is an FDA NDC product dict with product_ndc, generic_name, brand_name, etc.
product_ndc is used as the stable request_id.

Target table: mol_raw.fda_ndc (migration 126)
API endpoint: https://api.fda.gov/drug/ndc.json
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "fda_ndc"
BATCH_SIZE = 500

_SQL = """
    INSERT INTO mol_raw.fda_ndc (
        request_id,
        api_endpoint,
        api_version,
        request_params,
        response_status,
        response_body,
        response_body_hash,
        source_id
    ) VALUES (
        %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s
    )
    ON CONFLICT (request_id) DO UPDATE SET
        response_body       = EXCLUDED.response_body,
        response_body_hash  = EXCLUDED.response_body_hash,
        ingested_at         = NOW()
    WHERE mol_raw.fda_ndc.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def load_fda_ndc_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load FDA NDC product records into mol_raw.fda_ndc.

    Args:
        records:     List of NDC product dicts from FDANDCFetcher.
                     Each dict has product_ndc, generic_name, brand_name, etc.
        source_hash: Content hash for lineage tracking.
        batch_size:  Commit interval.

    Returns:
        Dict with status, records_fetched, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("FDA NDC loader: no records to load")
        return {"status": "success", "records_fetched": 0, "records_inserted": 0,
                "records_failed": 0, "errors": []}

    logger.info("Loading %d FDA NDC records into mol_raw.fda_ndc", len(records))

    inserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in enumerate(records):
                product_ndc = row.get("product_ndc") or f"ndc_row_{idx}"
                request_id = f"fda_ndc_{str(product_ndc).strip().replace('-', '_')}"
                body_json = json.dumps(row, default=str)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()

                try:
                    cur.execute(_SQL, (
                        request_id,
                        "https://api.fda.gov/drug/ndc.json",
                        "v1",
                        json.dumps({"product_ndc": product_ndc}),
                        200,
                        body_json,
                        body_hash,
                        SOURCE_ID,
                    ))
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()

                except Exception as e:
                    failed += 1
                    if len(errors) < 10:
                        errors.append({"index": idx, "product_ndc": product_ndc, "error": str(e)[:300]})
                    logger.error("FDA NDC record %s failed: %s", product_ndc, e)

            conn.commit()

    logger.info("FDA NDC load: %d inserted, %d failed", inserted, failed)
    return {
        "status": "success" if failed == 0 else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors,
    }
