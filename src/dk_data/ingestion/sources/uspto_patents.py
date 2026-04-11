"""USPTO Patents Data Loader.

Feature: 011-datasource-integration
Task: Phase 6 / US4 — credential-gated source (USPTO PatentsView)

Loads validated USPTO patent records into ip_raw.uspto_patents with
upsert semantics (ON CONFLICT DO UPDATE on patent_number).

Target table: ip_raw.uspto_patents (see migration 064_uspto_patents_raw_table.sql)
"""

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import USPTOPatentsRecord

logger = logging.getLogger(__name__)

# Batch commit interval
BATCH_SIZE = 500


def load_uspto_patents_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load USPTO patent records into mol_raw.uspto_patents.

    Validates each record using Pydantic and performs an upsert:
    INSERT ... ON CONFLICT (patent_number) DO UPDATE.

    Args:
        records: List of normalized patent record dicts from USPTOPatentsFetcher.
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
        logger.warning("No USPTO Patents records to load")
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info(
        "Loading %d USPTO Patents records into ip_raw.uspto_patents", len(records)
    )

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    # Validate with Pydantic
                    record = USPTOPatentsRecord(
                        patent_number=raw_record.get("patent_number", ""),
                        title=raw_record.get("title"),
                        abstract=raw_record.get("abstract"),
                        inventors=raw_record.get("inventors"),
                        assignees=raw_record.get("assignees"),
                        filing_date=_parse_date(raw_record.get("filing_date")),
                        grant_date=_parse_date(raw_record.get("grant_date")),
                        cpc_codes=raw_record.get("cpc_codes"),
                        claims_count=raw_record.get("claims_count"),
                        patent_type=raw_record.get("patent_type"),
                    )

                    # Serialize JSONB fields
                    inventors_json = (
                        json.dumps(record.inventors)
                        if record.inventors is not None
                        else None
                    )
                    assignees_json = (
                        json.dumps(record.assignees)
                        if record.assignees is not None
                        else None
                    )

                    cur.execute(
                        """
                        INSERT INTO ip_raw.uspto_patents (
                            patent_number, title, abstract,
                            inventors, assignees,
                            filing_date, grant_date,
                            cpc_codes, claims_count, patent_type,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s, %s,
                            %s, %s
                        )
                        ON CONFLICT (patent_number) DO UPDATE SET
                            title = EXCLUDED.title,
                            abstract = EXCLUDED.abstract,
                            inventors = EXCLUDED.inventors,
                            assignees = EXCLUDED.assignees,
                            filing_date = EXCLUDED.filing_date,
                            grant_date = EXCLUDED.grant_date,
                            cpc_codes = EXCLUDED.cpc_codes,
                            claims_count = EXCLUDED.claims_count,
                            patent_type = EXCLUDED.patent_type,
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash,
                            _loaded_at = NOW()
                        """,
                        (
                            record.patent_number,
                            record.title,
                            record.abstract,
                            inventors_json,
                            assignees_json,
                            record.filing_date,
                            record.grant_date,
                            record.cpc_codes if record.cpc_codes else None,
                            record.claims_count,
                            record.patent_type,
                            source_file or "patentsview_api",
                            source_hash,
                        ),
                    )
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()
                        logger.debug(
                            "Committed batch: %d records so far", records_inserted
                        )

                except ValidationError as e:
                    records_failed += 1
                    errors.append({
                        "index": idx,
                        "patent_number": raw_record.get("patent_number"),
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
                        "patent_number": raw_record.get("patent_number"),
                        "error": str(e),
                        "type": "database",
                    })
                    logger.error("Database error at index %d: %s", idx, e)

            # Final commit
            conn.commit()

    logger.info(
        "USPTO Patents load complete: %d upserted, %d failed",
        records_inserted,
        records_failed,
    )

    return {
        "status": "success" if records_inserted > 0 or records_failed == 0 else "failed",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10],
    }


def _parse_date(value: Any) -> Optional[date]:
    """Best-effort parsing of a date value from PatentsView.

    Accepts ISO strings (YYYY-MM-DD), datetime objects, date objects,
    or None.
    """
    if value is None:
        return None
    if isinstance(value, date):
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
