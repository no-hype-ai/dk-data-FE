"""UniProt protein data loader.

Feature: 012-platform-hardening (US3)

Loads UniProt protein records into raw.uniprot with upsert semantics.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import UniProtRecord

logger = logging.getLogger(__name__)


def load_uniprot_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load UniProt protein records into raw.uniprot.

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

                    validated = UniProtRecord(
                        accession=accession,
                        entry_name=raw_record.get("uniProtkbId", ""),
                        protein_name=protein_name,
                        gene_name=gene_primary,
                        organism=organism,
                        sequence_length=raw_record.get("sequence", {}).get("length"),
                        function_description=function_text,
                    )

                    cur.execute(
                        """
                        INSERT INTO raw.uniprot (
                            accession, entry_name, protein_name, gene_name,
                            organism, sequence_length, function_description,
                            raw_response, _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (accession) DO UPDATE SET
                            entry_name = EXCLUDED.entry_name,
                            protein_name = EXCLUDED.protein_name,
                            gene_name = EXCLUDED.gene_name,
                            organism = EXCLUDED.organism,
                            sequence_length = EXCLUDED.sequence_length,
                            function_description = EXCLUDED.function_description,
                            raw_response = EXCLUDED.raw_response,
                            _loaded_at = NOW(),
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash
                        """,
                        (
                            validated.accession, validated.entry_name,
                            validated.protein_name, validated.gene_name,
                            validated.organism, validated.sequence_length,
                            validated.function_description,
                            json.dumps(raw_record), source_file, source_hash,
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
