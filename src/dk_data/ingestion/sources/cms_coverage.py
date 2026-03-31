"""CMS Coverage loader — inserts to mol_raw.cms_coverage.

Feature: 021-post-deploy-fixes

Loads CMS Medicare Coverage Database records (NCDs, NCAs, Technology
Assessments) into mol_raw.cms_coverage as raw JSONB blobs.

ON CONFLICT on (response_body->>'id', response_body->>'_endpoint') updates
changed records while skipping unchanged ones.

Target table: mol_raw.cms_coverage
Unique index: uidx_mol_raw_cms_coverage_id_endpoint
  ON ((response_body->>'id'), (response_body->>'_endpoint'))
  WHERE id IS NOT NULL AND _endpoint IS NOT NULL
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_cursor

logger = logging.getLogger(__name__)


def load_cms_coverage_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Load CMS Coverage records into mol_raw.cms_coverage.

    Args:
        records: Records from CMSCoverageFetcher.fetch()['records'].
                 Each record must have 'id' and '_endpoint' fields.
        source_hash: Optional content hash for lineage tracking.

    Returns:
        Dict with status, records_fetched, records_inserted, records_updated, errors.
    """
    if not records:
        logger.info("No CMS Coverage records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info("Loading %d CMS Coverage records into mol_raw.cms_coverage", len(records))

    errors: List[str] = []
    inserted = 0
    skipped = 0

    sql = """
        INSERT INTO mol_raw.cms_coverage (response_body, source_id)
        VALUES (%s::JSONB, 'cms_coverage')
        ON CONFLICT ((response_body->>'id'), (response_body->>'_endpoint'))
        WHERE response_body->>'id' IS NOT NULL
          AND response_body->>'_endpoint' IS NOT NULL
        DO UPDATE SET
            response_body = EXCLUDED.response_body,
            ingested_at   = NOW()
        WHERE mol_raw.cms_coverage.response_body IS DISTINCT FROM EXCLUDED.response_body
    """

    with get_cursor() as cur:
        for record in records:
            coverage_id = record.get("id")
            endpoint = record.get("_endpoint")

            if not coverage_id or not endpoint:
                skipped += 1
                continue

            try:
                cur.execute(sql, (json.dumps(record),))
                inserted += 1
            except Exception as exc:
                errors.append(f"id={coverage_id} endpoint={endpoint}: {exc}")
                logger.warning(
                    "CMS Coverage insert error for id=%s endpoint=%s: %s",
                    coverage_id, endpoint, exc,
                )

    logger.info(
        "CMS Coverage load complete: %d inserted/updated, %d skipped (no id/endpoint), %d errors",
        inserted, skipped, len(errors),
    )

    return {
        "status": "success" if not errors else "partial",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
