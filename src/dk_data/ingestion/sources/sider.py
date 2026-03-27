"""SIDER side effect data loader.

Loads SIDER TSV records into raw.sider using the standard JSONB envelope
schema (migration 028_raw_layer_tables.sql).

Each TSV row is stored verbatim as response_body JSONB with exact SIDER
column names (stitch_id_flat, umls_cui_side_effect, side_effect_name,
lower_bound_freq, upper_bound_freq, etc.) so the bronze SQL model can
reference them correctly.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

_BASE_URL = "http://sideeffects.embl.de/media/files"


def load_sider_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 1000,
) -> Dict[str, Any]:
    """Load SIDER records into raw.sider (envelope schema).

    Each record dict (with SIDER TSV column names as keys) is stored as
    response_body JSONB in the standard envelope table.

    Args:
        records: Parsed SIDER rows from SIDERFetcher.fetch()['records'].
                 Keys are exact SIDER column names (stitch_id_flat,
                 umls_cui_side_effect, side_effect_name, etc.)
        source_hash: Content hash for tracking.
        source_file: Source file name ('meddra_freq.tsv' or 'meddra_all_se.tsv').
        batch_size: Commit batch size.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.info("No SIDER records to load")
        return {"status": "success", "records_inserted": 0, "records_failed": 0}

    logger.info(f"Loading {len(records)} SIDER records into raw.sider")

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    request_timestamp = datetime.now(timezone.utc)
    request_id = str(uuid.uuid4())

    # Determine API endpoint based on source file
    sf = source_file or "meddra_freq.tsv"
    api_endpoint = f"{_BASE_URL}/{sf}.gz"

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, record in enumerate(records):
                try:
                    stitch_id = record.get("stitch_id_flat")
                    umls_cui = record.get("umls_cui_side_effect")
                    if not stitch_id:
                        raise ValueError("Missing stitch_id_flat")

                    body_json = json.dumps(record)
                    body_hash = hashlib.sha256(body_json.encode()).hexdigest()

                    cur.execute(
                        """
                        INSERT INTO raw.sider (
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
                            FALSE, NOW(), 'sider'
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            f"{request_id}-{idx}",
                            request_timestamp,
                            api_endpoint,
                            "4.1",  # SIDER version
                            json.dumps({
                                "source_file": sf,
                                "source_hash": source_hash,
                                "stitch_id_flat": stitch_id,
                                "umls_cui_side_effect": umls_cui,
                            }),
                            200,
                            body_json,
                            body_hash,
                            len(body_json.encode()),
                        ),
                    )
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()
                        logger.info(
                            f"SIDER load progress: {records_inserted}/{len(records)}"
                        )

                except Exception as e:
                    records_failed += 1
                    errors.append({
                        "index": idx,
                        "stitch_id_flat": record.get("stitch_id_flat"),
                        "error": str(e),
                    })
                    if records_failed <= 10:
                        logger.warning(f"Error at index {idx}: {e}")

            conn.commit()

    logger.info(
        f"SIDER load complete: {records_inserted} inserted, {records_failed} failed"
    )
    return {
        "status": "success" if records_failed == 0 else "partial",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10] if errors else [],
    }
