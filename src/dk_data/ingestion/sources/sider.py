"""SIDER side effect data loader.

Loads SIDER TSV records into mol_raw.sider using the standard JSONB envelope
schema (migration 028_raw_layer_tables.sql).

Each TSV row is stored verbatim as response_body JSONB with exact SIDER
column names (stitch_id_flat, umls_cui_side_effect, side_effect_name,
lower_bound_freq, upper_bound_freq, etc.) so the bronze SQL model can
reference them correctly.

request_id format: sider_{source_file_tag}_{stitch_id_flat}_{umls_cui_side_effect}
Stable across re-runs so ON CONFLICT upsert deduplicates correctly.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

_BASE_URL = "http://sideeffects.embl.de/media/files"
BATCH_SIZE = 1000

# Short tag to distinguish rows from the two source files in request_id
_FILE_TAG = {
    "meddra_freq.tsv": "freq",
    "meddra_all_se.tsv": "allse",
}


def load_sider_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load SIDER records into mol_raw.sider (envelope schema).

    request_id = sider_{file_tag}_{stitch_id_flat}_{umls_cui_side_effect}
    This is stable across re-runs so the upsert correctly deduplicates.

    Args:
        records: Parsed SIDER rows from SIDERFetcher.fetch()['records'].
        source_hash: Content hash for tracking.
        source_file: Ignored — each record carries its own 'source_file' key.
        batch_size: Commit batch size.

    Returns:
        Dict with status, records_inserted, records_skipped, errors.
    """
    if not records:
        logger.info("No SIDER records to load")
        return {"status": "success", "records_inserted": 0, "records_skipped": 0}

    logger.info("Loading %d SIDER records into mol_raw.sider", len(records))

    request_timestamp = datetime.now(timezone.utc)
    records_inserted = 0
    records_skipped = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, record in enumerate(records):
                stitch_id = record.get("stitch_id_flat")
                umls_cui = record.get("umls_cui_side_effect", "")
                src_file = record.get("source_file", "meddra_freq.tsv")

                if not stitch_id:
                    records_skipped += 1
                    continue

                file_tag = _FILE_TAG.get(src_file, "unknown")
                request_id = f"sider_{file_tag}_{stitch_id}_{umls_cui or 'none'}"
                api_endpoint = f"{_BASE_URL}/{src_file}.gz"

                body_json = json.dumps(record)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()

                try:
                    cur.execute(
                        """
                        INSERT INTO mol_raw.sider (
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
                            200, %s, %s, %s,
                            FALSE, NOW(), 'sider'
                        )
                        ON CONFLICT (request_id)
                        DO UPDATE SET
                            response_body      = EXCLUDED.response_body,
                            response_body_hash = EXCLUDED.response_body_hash,
                            processed_to_bronze = FALSE,
                            ingested_at        = NOW()
                        WHERE mol_raw.sider.response_body_hash IS DISTINCT FROM EXCLUDED.response_body_hash
                        """,
                        (
                            request_id,
                            request_timestamp,
                            api_endpoint,
                            "4.1",
                            json.dumps({"source_file": src_file, "source_hash": source_hash}),
                            body_json,
                            body_hash,
                            len(body_json.encode()),
                        ),
                    )
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()
                        logger.info(
                            "SIDER load progress: %d/%d", records_inserted, len(records)
                        )

                except Exception as e:
                    conn.rollback()
                    records_skipped += 1
                    errors.append({"index": idx, "stitch_id_flat": stitch_id, "error": str(e)})
                    if len(errors) <= 10:
                        logger.warning("SIDER insert error for %s: %s", request_id, e)

            conn.commit()

    logger.info(
        "SIDER load complete: %d inserted, %d skipped", records_inserted, records_skipped
    )
    return {
        "status": "success" if not errors else "partial",
        "records_inserted": records_inserted,
        "records_skipped": records_skipped,
        "errors": errors[:10] if errors else [],
    }
