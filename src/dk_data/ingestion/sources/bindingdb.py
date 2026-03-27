"""BindingDB binding affinity data loader.

Loads BindingDB TSV records into mol_raw.bindingdb using the standard
JSONB envelope schema (migration 062_mol_source_raw_tables.sql).

Each TSV row is stored verbatim as response_body JSONB, preserving the
exact BindingDB column header strings so the bronze SQL model can
reference them with correct key names (e.g., "Ki (nM)", "Ligand InChIKey").

request_id format: bindingdb_{reactant_set_id}
Stable across re-runs so ON CONFLICT deduplicates correctly.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

_DOWNLOAD_URL = "https://www.bindingdb.org/bind/BindingDB_All.tsv.zip"
BATCH_SIZE = 1000


def load_bindingdb_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load BindingDB records into mol_raw.bindingdb (envelope schema).

    Each record dict (with BindingDB TSV column headers as keys) is
    stored as response_body JSONB in the standard envelope table.
    request_id = bindingdb_{reactant_set_id} — stable across re-runs,
    so the ON CONFLICT upsert deduplicates correctly.

    Args:
        records: Parsed BindingDB rows from BindingDBFetcher.fetch()['records'].
        source_hash: Content hash for tracking.
        source_file: Source file/run identifier.
        batch_size: Commit batch size.

    Returns:
        Dict with status, records_inserted, records_skipped, errors.
    """
    if not records:
        logger.info("No BindingDB records to load")
        return {"status": "success", "records_inserted": 0, "records_skipped": 0}

    logger.info("Loading %d BindingDB records into mol_raw.bindingdb", len(records))

    request_timestamp = datetime.now(timezone.utc)
    records_inserted = 0
    records_skipped = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, record in enumerate(records):
                reactant_id = record.get("BindingDB Reactant_set_id")
                if not reactant_id:
                    records_skipped += 1
                    continue

                request_id = f"bindingdb_{reactant_id}"
                body_json = json.dumps(record)
                body_hash = hashlib.sha256(body_json.encode()).hexdigest()

                try:
                    cur.execute(
                        """
                        INSERT INTO mol_raw.bindingdb (
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
                            FALSE, NOW(), 'bindingdb'
                        )
                        ON CONFLICT (request_id)
                        DO UPDATE SET
                            response_body      = EXCLUDED.response_body,
                            response_body_hash = EXCLUDED.response_body_hash,
                            processed_to_bronze = FALSE,
                            ingested_at        = NOW()
                        WHERE mol_raw.bindingdb.response_body_hash IS DISTINCT FROM EXCLUDED.response_body_hash
                        """,
                        (
                            request_id,
                            request_timestamp,
                            _DOWNLOAD_URL,
                            "2024",
                            json.dumps({
                                "source_hash": source_hash,
                                "reactant_id": reactant_id,
                            }),
                            body_json,
                            body_hash,
                            len(body_json.encode()),
                        ),
                    )
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()
                        logger.info(
                            "BindingDB load progress: %d/%d",
                            records_inserted, len(records),
                        )

                except Exception as e:
                    records_skipped += 1
                    errors.append({"index": idx, "reactant_id": reactant_id, "error": str(e)})
                    if len(errors) <= 10:
                        logger.warning("BindingDB insert error for %s: %s", request_id, e)

            conn.commit()

    logger.info(
        "BindingDB load complete: %d inserted, %d skipped",
        records_inserted, records_skipped,
    )
    return {
        "status": "success" if not errors else "partial",
        "records_inserted": records_inserted,
        "records_skipped": records_skipped,
        "errors": errors[:10] if errors else [],
    }
