"""IMGT loader — inserts gene sequence records into mol_raw.imgt.

Each record from IMGTFetcher represents one gene group (e.g., IGHV) and
contains the raw FASTA sequence text plus metadata. The gene_group name
is used as the stable request_id.

Target table: mol_raw.imgt (migration 096)
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_connection

logger = logging.getLogger(__name__)

SOURCE_ID = "imgt"
BATCH_SIZE = 100

_SQL = """
    INSERT INTO mol_raw.imgt (
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
    WHERE mol_raw.imgt.response_body IS DISTINCT FROM EXCLUDED.response_body
"""


def load_imgt_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load IMGT gene sequence records into mol_raw.imgt.

    Args:
        records:     List of gene-group dicts from IMGTFetcher.
        source_hash: Content hash for lineage tracking.
        batch_size:  Commit interval.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("IMGT loader: no records to load")
        return {"status": "success", "records_fetched": 0, "records_inserted": 0, "records_failed": 0, "errors": []}

    logger.info("Loading %d IMGT gene group records into mol_raw.imgt", len(records))

    inserted = 0
    failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, row in enumerate(records):
                gene_group = row.get("gene_group", f"group_{idx}")
                species = row.get("species", "Homo sapiens").replace(" ", "_")
                request_id = f"imgt_{species}_{gene_group}"

                # Store body without the large FASTA string duplicated in hash computation
                body_json = json.dumps(row)
                body_hash = hashlib.sha256(
                    (gene_group + str(row.get("allele_count", 0))).encode()
                ).hexdigest()

                try:
                    cur.execute(_SQL, (
                        request_id,
                        row.get("source_url", "https://www.imgt.org/genedb/GENElect"),
                        "v1",
                        json.dumps({"source_hash": source_hash, "gene_group": gene_group}),
                        200,
                        body_json,
                        body_hash,
                        SOURCE_ID,
                    ))
                    inserted += 1

                    if inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("IMGT: committed %d records", inserted)

                except Exception as exc:
                    failed += 1
                    errors.append({"index": idx, "gene_group": gene_group, "error": str(exc), "type": "database"})
                    logger.error("IMGT insert error at index %d: %s", idx, exc)

            conn.commit()

    logger.info("IMGT load complete: %d inserted, %d failed", inserted, failed)
    return {
        "status": "success" if failed == 0 or inserted > 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_failed": failed,
        "errors": errors[:10],
    }
