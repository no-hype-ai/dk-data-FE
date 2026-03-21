"""UniProt protein data loader.

Feature: 012-platform-hardening (US3)

Loads UniProt protein records into raw.uniprot.

The raw.uniprot table uses an API-response logging schema with columns like
request_id, api_endpoint, response_status, response_body (JSONB), etc.
Each protein record from the fetcher is stored as a separate row with
the full API record as response_body and the accession as request_id.
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import UniProtRecord

logger = logging.getLogger(__name__)

API_ENDPOINT = "https://rest.uniprot.org/uniprotkb/search"


def load_uniprot_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load UniProt protein records into raw.uniprot.

    Each record is stored as a row in the API response logging table.
    The full protein JSON is stored in response_body, with the accession
    used as request_id for deduplication.

    Args:
        records: Protein records from UniProtFetcher.fetch().
        source_hash: Content hash for tracking.
        source_file: Source file identifier.
        batch_size: Commit batch size.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.info("No UniProt records to load")
        return {"status": "success", "records_inserted": 0, "records_failed": 0}

    logger.info(f"Loading {len(records)} UniProt records into raw.uniprot")

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    accession = raw_record.get("primaryAccession", "")

                    # Validate the record can be parsed (keeps validation logic)
                    gene_names = raw_record.get("genes", [{}])
                    gene_primary = gene_names[0].get("geneName", {}).get("value") if gene_names else None
                    protein_name = (
                        raw_record.get("proteinDescription", {})
                        .get("recommendedName", {})
                        .get("fullName", {})
                        .get("value")
                    )
                    organism = raw_record.get("organism", {}).get("scientificName")
                    function_text = None
                    for comment in raw_record.get("comments", []):
                        if comment.get("commentType") == "FUNCTION":
                            texts = comment.get("texts", [])
                            if texts:
                                function_text = texts[0].get("value")
                            break

                    # Validate through Pydantic (ensures accession is non-empty, etc.)
                    UniProtRecord(
                        accession=accession,
                        entry_name=raw_record.get("uniProtkbId", ""),
                        protein_name=protein_name,
                        gene_name=gene_primary,
                        organism=organism,
                        sequence_length=raw_record.get("sequence", {}).get("length"),
                        function_description=function_text,
                    )

                    response_body = json.dumps(raw_record)
                    body_hash = hashlib.md5(response_body.encode()).hexdigest()

                    cur.execute(
                        """
                        INSERT INTO mol_raw.uniprot (
                            request_id, api_endpoint, response_status,
                            response_body, response_body_hash,
                            response_size_bytes, source_id
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            accession,
                            API_ENDPOINT,
                            200,
                            response_body,
                            body_hash,
                            len(response_body),
                            "uniprot",
                        ),
                    )
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()

                except (ValidationError, Exception) as e:
                    records_failed += 1
                    errors.append({"index": idx, "accession": raw_record.get("primaryAccession"), "error": str(e)})
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
