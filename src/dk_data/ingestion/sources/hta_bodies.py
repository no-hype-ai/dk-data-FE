"""HTA Bodies Decision Loader.

Feature: 011-datasource-integration
Task: T058-T060 — HTA Bodies CI source integration

Loads normalized HTA decision records into raw.hta_decisions with
upsert semantics (ON CONFLICT DO UPDATE on decision_id).

Target table: raw.hta_decisions (see migration 060_ci_source_tables.sql)
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import HTADecisionRecord

logger = logging.getLogger(__name__)

# Batch commit interval
BATCH_SIZE = 500


def load_hta_decisions_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load HTA decision records into raw.hta_decisions.

    Validates each record via the HTADecisionRecord Pydantic model and
    performs an upsert: INSERT ... ON CONFLICT (decision_id) DO UPDATE.

    Args:
        records: List of decision record dicts from HTABodiesFetcher.
        source_hash: Optional content hash for tracking.
        source_file: Optional source file identifier.
        batch_size: Number of records to commit at once.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.info("No HTA decision records to load")
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info("Loading %d HTA decision records into raw.hta_decisions", len(records))

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    # Validate via Pydantic model
                    validated = HTADecisionRecord(
                        decision_id=raw_record.get("decision_id", ""),
                        agency=raw_record.get("agency", ""),
                        drug_name=raw_record.get("drug_name"),
                        indication=raw_record.get("indication"),
                        decision_type=raw_record.get("decision_type"),
                        decision_date=_parse_date(
                            raw_record.get("decision_date")
                        ),
                        document_url=raw_record.get("document_url"),
                        summary=raw_record.get("summary"),
                    )

                    cur.execute(
                        """
                        INSERT INTO raw.hta_decisions (
                            decision_id, agency, drug_name,
                            indication, decision_type, decision_date,
                            document_url, summary,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s
                        )
                        ON CONFLICT (decision_id) DO UPDATE SET
                            agency = EXCLUDED.agency,
                            drug_name = EXCLUDED.drug_name,
                            indication = EXCLUDED.indication,
                            decision_type = EXCLUDED.decision_type,
                            decision_date = EXCLUDED.decision_date,
                            document_url = EXCLUDED.document_url,
                            summary = EXCLUDED.summary,
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash,
                            _loaded_at = NOW()
                        """,
                        (
                            validated.decision_id,
                            validated.agency,
                            validated.drug_name,
                            validated.indication,
                            validated.decision_type,
                            validated.decision_date,
                            validated.document_url,
                            validated.summary,
                            source_file or f"hta_{validated.agency}_api",
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
                        "decision_id": raw_record.get("decision_id"),
                        "error": str(e),
                    })
                    if records_failed <= 5:
                        logger.warning(
                            "Validation error at index %d (decision_id=%s): %s",
                            idx, raw_record.get("decision_id"), e,
                        )

                except Exception as e:
                    records_failed += 1
                    errors.append({
                        "index": idx,
                        "decision_id": raw_record.get("decision_id"),
                        "error": str(e),
                    })
                    logger.error(
                        "Error at index %d (decision_id=%s): %s",
                        idx, raw_record.get("decision_id"), e,
                    )

            # Final commit
            conn.commit()

    logger.info(
        "HTA decisions load complete: %d inserted, %d failed",
        records_inserted, records_failed,
    )

    return {
        "status": "success" if records_failed == 0 else "partial",
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
