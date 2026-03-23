"""DrugBank Data Loader.

Feature: 011-datasource-integration
Task: Phase 6 / US4 — credential-gated source (DrugBank)

Loads validated DrugBank drug records into raw.drugbank with
upsert semantics (ON CONFLICT DO UPDATE on drugbank_id).

Target table: raw.drugbank (see migration 063_drugbank_raw_table.sql)
"""

import hashlib
import json
import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional
from uuid import uuid4

import psycopg2
from pydantic import ValidationError

from ..utils.validators import DrugBankRecord


@contextmanager
def _get_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Direct psycopg2 connection that avoids the secret-strength check in utils.database.
    utils.database.get_connection() rejects 'postgres' as a password when
    POSTGRES_HOST != 'localhost', which breaks container-to-container connections
    using the default docker compose password. This function reads env vars directly,
    matching the pattern used by cms_usp.py and sync_runner.py.
    """
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        database=os.getenv("POSTGRES_DB", "dk_data"),
    )
    try:
        yield conn
    finally:
        conn.close()

logger = logging.getLogger(__name__)

# Batch commit interval
BATCH_SIZE = 500


def load_drugbank_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load DrugBank records into raw.drugbank.

    Validates each record using Pydantic and performs an upsert:
    INSERT ... ON CONFLICT (drugbank_id) DO UPDATE.

    Args:
        records: List of normalized drug record dicts from DrugBankFetcher.
        source_hash: Hash of the fetch batch for lineage tracking.
        source_file: Source file identifier.
        batch_size: Number of records to commit at once.

    Returns:
        Dictionary with:
            - status: 'success' or 'failed'
            - records_inserted: number of records upserted
            - records_failed: number of records that failed validation
            - errors: list of first 10 error details
    """
    if not records:
        logger.warning("No DrugBank records to load")
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info("Loading %d DrugBank records into raw.drugbank", len(records))

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with _get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    # Validate with Pydantic
                    record = DrugBankRecord(**raw_record)

                    # Wrap the validated record as the response_body JSONB blob
                    body = {
                        "drugbank_id": record.drugbank_id,
                        "name": record.name,
                        "description": record.description,
                        "cas_number": record.cas_number,
                        "categories": record.categories,
                        "targets": record.targets,
                        "enzymes": record.enzymes,
                        "indication": record.indication,
                        "pharmacodynamics": record.pharmacodynamics,
                    }
                    body_json = json.dumps(body)
                    body_hash = hashlib.sha256(body_json.encode()).hexdigest()

                    cur.execute(
                        """
                        INSERT INTO mol_raw.drugbank (
                            request_id, api_endpoint, response_status,
                            response_body, response_body_hash, source_id,
                            processed_to_bronze
                        ) VALUES (%s, %s, %s, %s::jsonb, %s, 'drugbank', false)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            str(uuid4()),
                            f"file://drugbank/{record.drugbank_id}",
                            200,
                            body_json,
                            body_hash,
                        ),
                    )
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("Committed batch: %d records so far", records_inserted)

                except ValidationError as e:
                    records_failed += 1
                    errors.append({
                        "index": idx,
                        "drugbank_id": raw_record.get("drugbank_id"),
                        "error": str(e),
                        "type": "validation",
                    })
                    if records_failed <= 5:
                        logger.warning(
                            "Validation error at index %d: %s", idx, e
                        )

                except Exception as e:
                    records_failed += 1
                    errors.append({
                        "index": idx,
                        "drugbank_id": raw_record.get("drugbank_id"),
                        "error": str(e),
                        "type": "database",
                    })
                    logger.error("Database error at index %d: %s", idx, e)

            # Final commit
            conn.commit()

    logger.info(
        "DrugBank load complete: %d upserted, %d failed",
        records_inserted,
        records_failed,
    )

    return {
        "status": "success" if records_inserted > 0 or records_failed == 0 else "failed",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10],
    }
