"""BindingDB binding affinity data loader.

Loads BindingDB TSV records into raw.bindingdb using the standard
JSONB envelope schema (migration 062_mol_source_raw_tables.sql).

Each TSV row is stored verbatim as response_body JSONB, preserving the
exact BindingDB column header strings so the bronze SQL model can
reference them with correct key names (e.g., "Ki (nM)", "Ligand InChIKey").
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

_DOWNLOAD_URL = "https://www.bindingdb.org/bind/BindingDB_All.tsv.zip"


def load_bindingdb_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 1000,
) -> Dict[str, Any]:
    """Load BindingDB records into raw.bindingdb (envelope schema).

    Each record dict (with BindingDB TSV column headers as keys) is
    stored as response_body JSONB in the standard envelope table.

    Args:
        records: Parsed BindingDB rows from BindingDBFetcher.fetch()['records'].
                 Keys are exact BindingDB TSV column headers.
        source_hash: Content hash for tracking.
        source_file: Source file/run identifier.
        batch_size: Commit batch size.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.info("No BindingDB records to load")
        return {"status": "success", "records_inserted": 0, "records_failed": 0}

    logger.info(f"Loading {len(records)} BindingDB records into raw.bindingdb")

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    request_timestamp = datetime.now(timezone.utc)
    request_id = str(uuid.uuid4())

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, record in enumerate(records):
                try:
                    bindingdb_id = record.get("BindingDB Reactant_set_id")
                    if not bindingdb_id:
                        raise ValueError("Missing BindingDB Reactant_set_id")

                    body_json = json.dumps(record)
                    body_hash = hashlib.sha256(body_json.encode()).hexdigest()

                    cur.execute(
                        """
                        INSERT INTO raw.bindingdb (
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
                            FALSE, NOW(), 'bindingdb'
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            f"{request_id}-{idx}",
                            request_timestamp,
                            _DOWNLOAD_URL,
                            "2024",
                            json.dumps({
                                "source_file": source_file,
                                "source_hash": source_hash,
                                "bindingdb_id": bindingdb_id,
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
                            f"BindingDB load progress: {records_inserted}/{len(records)}"
                        )

                except Exception as e:
                    records_failed += 1
                    errors.append({
                        "index": idx,
                        "bindingdb_id": record.get("BindingDB Reactant_set_id"),
                        "error": str(e),
                    })
                    if records_failed <= 10:
                        logger.warning(f"Error at index {idx}: {e}")

            conn.commit()

    logger.info(
        f"BindingDB load complete: {records_inserted} inserted, {records_failed} failed"
    )
    return {
        "status": "success" if records_failed == 0 else "partial",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10] if errors else [],
    }
