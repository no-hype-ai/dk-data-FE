"""TDC ADMET loader — inserts to mol_raw.tdc_admet.

Feature: 019-cms-puf-platform-reconciliation

Loads Therapeutics Data Commons ADMET benchmark dataset records (raw JSONB
from TDCADMETFetcher) into mol_raw.tdc_admet.

Each dataset from the fetcher is stored as one row. The response_body JSONB
contains the full dataset dict:
    {
        "dataset_name": "Caco2_Wang",
        "data": [{"Drug_ID": "...", "Drug": "...", "Y": ..., ...}, ...]
    }

The request_params column stores {"dataset": "<dataset_name>"} so the bronze
SQLMesh model can extract dataset_name without parsing response_body.

Target table: mol_raw.tdc_admet
Schema (migration 089_entity_linking_gaps.sql):
    id                  BIGSERIAL PRIMARY KEY
    request_id          TEXT NOT NULL
    request_timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    request_params      JSONB
    api_endpoint        TEXT
    response_status     INTEGER NOT NULL DEFAULT 200
    response_body       JSONB NOT NULL
    response_body_hash  TEXT
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE
    source_id           TEXT NOT NULL DEFAULT 'tdc_admet'
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()

Unique index: ON (request_id) — one row per dataset per fetch run.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "tdc_admet"
API_ENDPOINT = "https://dataverse.harvard.edu/api/access/datafile/"
BATCH_SIZE = 50  # datasets per commit; typical runs have ~20 datasets


def load_tdc_admet_data(
    records_or_conn: Any,
    data: Optional[Dict[str, Any]] = None,
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load TDC ADMET dataset records into mol_raw.tdc_admet.

    Supports both calling conventions:
      New (orchestrator): load_tdc_admet_data(records_list, source_hash=hash)
      Old: load_tdc_admet_data(conn, data_dict)

    Returns:
        Dict with:
            records_inserted: number of dataset rows inserted or updated
            records_skipped:  number of dataset rows skipped (no change)
    """
    if isinstance(records_or_conn, list):
        records: List[Dict[str, Any]] = records_or_conn
    else:
        records = (data or {}).get("records", []) if data else []

    if not records:
        logger.info("TDC ADMET: no records to load")
        return {"status": "success", "records_inserted": 0, "records_skipped": 0, "records_fetched": 0}

    logger.info(
        "TDC ADMET: loading %d dataset(s) into mol_raw.tdc_admet", len(records)
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    sql = """
        INSERT INTO mol_raw.tdc_admet (
            request_id,
            request_timestamp,
            request_params,
            api_endpoint,
            response_status,
            response_body,
            response_body_hash,
            processed_to_bronze,
            source_id
        ) VALUES (
            %s,
            NOW(),
            %s::JSONB,
            %s,
            200,
            %s::JSONB,
            %s,
            FALSE,
            %s
        )
        ON CONFLICT (request_id)
        DO UPDATE SET
            response_body       = EXCLUDED.response_body,
            response_body_hash  = EXCLUDED.response_body_hash,
            ingested_at         = NOW()
        WHERE mol_raw.tdc_admet.response_body IS DISTINCT FROM EXCLUDED.response_body
    """

    inserted = 0
    skipped = 0

    def _run(connection: Any) -> None:
        nonlocal inserted, skipped
        with connection.cursor() as cur:
            for idx, record in enumerate(records):
                dataset_name = record.get("dataset_name")
                if not dataset_name:
                    logger.warning(
                        "TDC ADMET: record at index %d has no dataset_name — skipping",
                        idx,
                    )
                    skipped += 1
                    continue

                request_id = f"tdc_admet_{dataset_name}_{timestamp}"
                request_params = json.dumps({"dataset": dataset_name})
                response_body_str = json.dumps(record, ensure_ascii=False)
                body_hash = hashlib.sha256(response_body_str.encode()).hexdigest()

                try:
                    cur.execute(
                        sql,
                        (
                            request_id,
                            request_params,
                            API_ENDPOINT,
                            response_body_str,
                            body_hash,
                            SOURCE_ID,
                        ),
                    )
                    # rowcount == 0 means ON CONFLICT fired but DO UPDATE WHERE
                    # clause was false (no change) — count as skipped
                    if cur.rowcount and cur.rowcount > 0:
                        inserted += 1
                    else:
                        skipped += 1

                except Exception as exc:
                    logger.error(
                        "TDC ADMET: insert error for dataset '%s': %s",
                        dataset_name,
                        exc,
                    )
                    connection.rollback()
                    skipped += 1
                    continue

                if (idx + 1) % BATCH_SIZE == 0:
                    connection.commit()
                    logger.debug(
                        "TDC ADMET: committed batch — %d inserted so far", inserted
                    )

            connection.commit()

    if isinstance(records_or_conn, list):
        with get_connection() as new_conn:
            _run(new_conn)
    else:
        _run(records_or_conn)

    logger.info(
        "TDC ADMET load complete: %d inserted/updated, %d skipped",
        inserted,
        skipped,
    )

    return {"status": "success", "records_inserted": inserted, "records_skipped": skipped, "records_fetched": inserted + skipped}
