"""ORCID researcher profile data loader.

Feature: 012-platform-hardening (US3)

Loads ORCID researcher profiles into raw.orcid with upsert semantics.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import ORCIDRecord

logger = logging.getLogger(__name__)


def load_orcid_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load ORCID researcher profiles into raw.orcid.

    Args:
        records: Profile records from ORCIDFetcher.fetch().
        source_hash: Content hash for tracking.
        source_file: Source file identifier.
        batch_size: Commit batch size.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.info("No ORCID records to load")
        return {"status": "success", "records_inserted": 0, "records_failed": 0}

    logger.info(f"Loading {len(records)} ORCID records into raw.orcid")

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    works = raw_record.get("works_count", [])
                    works_count = len(works) if isinstance(works, list) else works

                    validated = ORCIDRecord(
                        orcid_id=raw_record.get("orcid_id", ""),
                        given_names=raw_record.get("given_names"),
                        family_name=raw_record.get("family_name"),
                        credit_name=raw_record.get("credit_name"),
                    )

                    cur.execute(
                        """
                        INSERT INTO raw.orcid (
                            orcid_id, given_names, family_name, credit_name,
                            biography, keywords, current_affiliations,
                            works_count, external_ids, raw_response
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (orcid_id) DO UPDATE SET
                            given_names = EXCLUDED.given_names,
                            family_name = EXCLUDED.family_name,
                            credit_name = EXCLUDED.credit_name,
                            biography = EXCLUDED.biography,
                            keywords = EXCLUDED.keywords,
                            current_affiliations = EXCLUDED.current_affiliations,
                            works_count = EXCLUDED.works_count,
                            external_ids = EXCLUDED.external_ids,
                            raw_response = EXCLUDED.raw_response,
                            fetched_at = NOW()
                        """,
                        (
                            validated.orcid_id, validated.given_names,
                            validated.family_name, validated.credit_name,
                            raw_record.get("biography"),
                            json.dumps(raw_record.get("keywords", [])),
                            json.dumps(raw_record.get("current_affiliations", [])),
                            works_count,
                            json.dumps(raw_record.get("external_ids", {})),
                            json.dumps(raw_record.get("raw_response", {})),
                        ),
                    )
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()

                except (ValidationError, Exception) as e:
                    records_failed += 1
                    errors.append({"index": idx, "orcid_id": raw_record.get("orcid_id"), "error": str(e)})
                    if records_failed <= 10:
                        logger.warning(f"Error at index {idx}: {e}")

            conn.commit()

    logger.info(f"ORCID load complete: {records_inserted} inserted, {records_failed} failed")
    return {
        "status": "success" if records_failed == 0 else "partial",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10] if errors else [],
    }
