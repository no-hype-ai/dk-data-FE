"""UniProt protein data loader.

Feature: 012-platform-hardening (US3)

Loads UniProt protein records into mol_raw.uniprot using the standard JSONB
envelope schema (response_body, response_status, api_endpoint, etc.)
matching migration 028_raw_layer_tables.sql.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

# UniProt REST API base URL for constructing the endpoint field
_BASE_URL = "https://rest.uniprot.org/uniprotkb"


def load_uniprot_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load UniProt protein records into mol_raw.uniprot (envelope schema).

    Each API record is stored as a full JSONB blob in response_body,
    matching the envelope pattern defined in migration 028_raw_layer_tables.

    Args:
        records: Protein records from UniProtFetcher.fetch()['records'].
                 Each element is the full UniProt JSON object for one protein.
        source_hash: Content hash for tracking (becomes response_body_hash).
        source_file: Source file/run identifier (stored in api_endpoint).
        batch_size: Commit batch size.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.info("No UniProt records to load")
        return {"status": "success", "records_inserted": 0, "records_failed": 0}

    logger.info(f"Loading {len(records)} UniProt records into mol_raw.uniprot")

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    request_timestamp = datetime.now(timezone.utc)
    request_id = str(uuid.uuid4())

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, record in enumerate(records):
                try:
                    accession = record.get("primaryAccession", "")
                    if not accession:
                        raise ValueError("Missing primaryAccession")

                    body_json = json.dumps(record)
                    body_hash = hashlib.sha256(body_json.encode()).hexdigest()
                    api_endpoint = f"{_BASE_URL}/{accession}"

                    cur.execute(
                        """
                        INSERT INTO mol_raw.uniprot (
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
                            FALSE, NOW(), 'uniprot'
                        )
                        ON CONFLICT (response_body_hash) DO NOTHING
                        """,
                        (
                            f"{request_id}-{idx}",
                            request_timestamp,
                            api_endpoint,
                            "2024-01",  # UniProt REST API version
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
                        "accession": record.get("primaryAccession"),
                        "error": str(e),
                    })
                    if records_failed <= 10:
                        logger.warning(f"Error at index {idx}: {e}")

            conn.commit()

    logger.info(f"UniProt load complete: {records_inserted} inserted, {records_failed} failed")
    return {
        "status": "success" if records_failed == 0 else "partial",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10] if errors else [],
    }
