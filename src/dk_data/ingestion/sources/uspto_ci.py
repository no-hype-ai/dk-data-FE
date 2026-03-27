"""USPTO CI Source Loader.

Feature: 011-datasource-integration
Task: T055-T057 — USPTO PatentsView CI source integration

Loads normalized USPTO patent records into mol_raw.uspto_ci with upsert
semantics (ON CONFLICT DO UPDATE on patent_id).

Target table: mol_raw.uspto_ci (see migration 060_ci_source_tables.sql)
"""

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import USPTOCIRecord

logger = logging.getLogger(__name__)

# Batch commit interval
BATCH_SIZE = 500


def load_uspto_ci_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load USPTO CI patent records into mol_raw.uspto_ci.

    Validates each record via the USPTOCIRecord Pydantic model and
    performs an upsert: INSERT ... ON CONFLICT (patent_id) DO UPDATE.

    Args:
        records: List of patent record dicts from USPTOCIFetcher.
        source_hash: Optional content hash for tracking.
        source_file: Optional source file identifier.
        batch_size: Number of records to commit at once.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.info("No USPTO CI records to load")
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info("Loading %d USPTO CI records into mol_raw.uspto_ci", len(records))

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    # Validate via Pydantic model
                    validated = USPTOCIRecord(
                        patent_id=raw_record.get("patent_id", ""),
                        title=raw_record.get("title"),
                        abstract=raw_record.get("abstract"),
                        inventors=raw_record.get("inventors"),
                        assignees=raw_record.get("assignees"),
                        filing_date=_parse_date(raw_record.get("filing_date")),
                        grant_date=_parse_date(raw_record.get("grant_date")),
                        cpc_codes=raw_record.get("cpc_codes"),
                        claims_count=raw_record.get("claims_count"),
                    )

                    # Serialize JSONB fields
                    inventors_json = (
                        json.dumps(validated.inventors)
                        if validated.inventors is not None
                        else None
                    )
                    assignees_json = (
                        json.dumps(validated.assignees)
                        if validated.assignees is not None
                        else None
                    )

                    cur.execute(
                        """
                        INSERT INTO mol_raw.uspto_ci (
                            patent_id, title, abstract,
                            inventors, assignees,
                            filing_date, grant_date,
                            cpc_codes, claims_count,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s
                        )
                        ON CONFLICT (patent_id) DO UPDATE SET
                            title = EXCLUDED.title,
                            abstract = EXCLUDED.abstract,
                            inventors = EXCLUDED.inventors,
                            assignees = EXCLUDED.assignees,
                            filing_date = EXCLUDED.filing_date,
                            grant_date = EXCLUDED.grant_date,
                            cpc_codes = EXCLUDED.cpc_codes,
                            claims_count = EXCLUDED.claims_count,
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash,
                            _loaded_at = NOW()
                        """,
                        (
                            validated.patent_id,
                            validated.title,
                            validated.abstract,
                            inventors_json,
                            assignees_json,
                            validated.filing_date,
                            validated.grant_date,
                            validated.cpc_codes if validated.cpc_codes else None,
                            validated.claims_count,
                            source_file or "uspto_patentsview_api",
                            source_hash,
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
                        "patent_id": raw_record.get("patent_id"),
                        "error": str(e),
                    })
                    if records_failed <= 5:
                        logger.warning(
                            "Validation error at index %d (patent_id=%s): %s",
                            idx, raw_record.get("patent_id"), e,
                        )

                except Exception as e:
                    records_failed += 1
                    errors.append({
                        "index": idx,
                        "patent_id": raw_record.get("patent_id"),
                        "error": str(e),
                    })
                    logger.error(
                        "Error at index %d (patent_id=%s): %s",
                        idx, raw_record.get("patent_id"), e,
                    )

            # Final commit
            conn.commit()

    logger.info(
        "USPTO CI load complete: %d inserted, %d failed",
        records_inserted, records_failed,
    )

    return {
        "status": "success" if records_inserted > 0 or records_failed == 0 else "failed",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10],
    }


def _parse_date(value: Any) -> Optional[date]:
    """Best-effort parsing of a date value.

    Accepts ISO strings (YYYY-MM-DD), datetime objects, date objects,
    or None.
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                return datetime.strptime(value[: len(fmt.replace("%", "0"))], fmt).date()
            except (ValueError, IndexError):
                continue
        try:
            return datetime.fromisoformat(value).date()
        except (ValueError, TypeError):
            pass
    return None
