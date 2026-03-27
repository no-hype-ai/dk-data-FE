"""PDB structure data loader.

Feature: 012-platform-hardening (US3)

Loads PDB structure records into raw.pdb using the standard JSONB
envelope schema (response_body, response_status, api_endpoint, etc.)
matching migration 028_raw_layer_tables.sql.

The fetcher returns a list of records, each containing:
  - pdb_id: str (4-char PDB ID)
  - title: str | None
  - method: str | None   (from exptl[0].method)
  - resolution: float | None  (from rcsb_entry_info.resolution_combined[0])
  - deposit_date: str | None  (from rcsb_accession_info.deposit_date)
  - raw_response: dict  (full RCSB JSON response)

Each record's raw_response is stored as response_body.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

_DATA_URL = "https://data.rcsb.org/rest/v1/core/entry"


def load_pdb_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load PDB structure records into raw.pdb (envelope schema).

    Each fetcher record's raw_response (full RCSB JSON) is stored as
    response_body, matching the envelope pattern from migration 028.

    Args:
        records: Structure records from PDBFetcher.fetch()['records'].
                 Each element has keys: pdb_id, title, method, resolution,
                 deposit_date, raw_response.
        source_hash: Content hash for tracking.
        source_file: Source file/run identifier.
        batch_size: Commit batch size.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.info("No PDB records to load")
        return {"status": "success", "records_inserted": 0, "records_failed": 0}

    logger.info(f"Loading {len(records)} PDB records into raw.pdb")

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    request_timestamp = datetime.now(timezone.utc)
    request_id = str(uuid.uuid4())

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, fetcher_record in enumerate(records):
                try:
                    pdb_id = fetcher_record.get("pdb_id", "")
                    if not pdb_id:
                        raise ValueError("Missing pdb_id")

                    # Store the full RCSB JSON response as response_body
                    raw_resp = fetcher_record.get("raw_response", {})
                    body_json = json.dumps(raw_resp)
                    body_hash = hashlib.sha256(body_json.encode()).hexdigest()
                    api_endpoint = f"{_DATA_URL}/{pdb_id}"

                    cur.execute(
                        """
                        INSERT INTO raw.pdb (
                            request_id,
                            request_timestamp,
                            api_endpoint,
                            api_version,
                            request_params,
                            response_status,
                            response_body,
                            response_body_hash,
                            response_size_bytes,
                            processed_to_bronze,
                            ingested_at,
                            source_id
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            FALSE, NOW(), 'pdb'
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            f"{request_id}-{idx}",
                            request_timestamp,
                            api_endpoint,
                            "v1",
                            json.dumps({"source_file": source_file, "source_hash": source_hash}),
                            200,
                            body_json,
                            body_hash,
                            len(body_json.encode()),
                        ),
                    )
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()

                except Exception as e:
                    records_failed += 1
                    errors.append({
                        "index": idx,
                        "pdb_id": fetcher_record.get("pdb_id"),
                        "error": str(e),
                    })
                    if records_failed <= 10:
                        logger.warning(f"Error at index {idx}: {e}")

            conn.commit()

    logger.info(f"PDB load complete: {records_inserted} inserted, {records_failed} failed")
    return {
        "status": "success" if records_failed == 0 else "partial",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10] if errors else [],
    }
