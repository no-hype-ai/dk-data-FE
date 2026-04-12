"""USPTO Trademark Data Loader.

Feature: 014-uspto-euipo-model-datasource
Task: T012 — USPTO trademark raw table loader

Loads normalised USPTO TSDR trademark records into ip_raw.uspto_trademarks
with upsert semantics (ON CONFLICT DO UPDATE on serial_number).
Tracks status changes in ip_raw.trademark_status_history.

Target table: ip_raw.uspto_trademarks (see migration 071_uspto_trademarks_raw.sql)
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import USPTOTrademarkRecord

logger = logging.getLogger(__name__)

# Batch commit interval
BATCH_SIZE = 500


def load_uspto_trademarks_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load USPTO trademark records into ip_raw.uspto_trademarks.

    Validates each record using Pydantic and performs an upsert:
    INSERT ... ON CONFLICT (serial_number) DO UPDATE.
    After upsert, checks for status changes and inserts history rows.

    Args:
        records: List of normalised trademark dicts from USPTOTrademarksFetcher.
        source_hash: Optional content hash for lineage tracking.
        source_file: Optional source file identifier.
        batch_size: Number of records to commit at once.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("No USPTO trademark records to load")
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info("Loading %d USPTO trademark records into ip_raw.uspto_trademarks", len(records))

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    # Parse dates before Pydantic validation
                    for date_field in ("status_date", "filing_date", "registration_date"):
                        raw_record[date_field] = _parse_date(raw_record.get(date_field))

                    # Validate with Pydantic
                    record = USPTOTrademarkRecord(**raw_record)

                    cur.execute(
                        """
                        INSERT INTO ip_raw.uspto_trademarks (
                            serial_number, mark_element, mark_type,
                            status, status_code, status_date,
                            filing_date, registration_number, registration_date,
                            nice_classes, us_classes,
                            owner_name, owner_entity_type,
                            goods_and_services, description_of_mark,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s
                        )
                        ON CONFLICT (serial_number) DO UPDATE SET
                            mark_element = EXCLUDED.mark_element,
                            mark_type = EXCLUDED.mark_type,
                            status = EXCLUDED.status,
                            status_code = EXCLUDED.status_code,
                            status_date = EXCLUDED.status_date,
                            filing_date = EXCLUDED.filing_date,
                            registration_number = EXCLUDED.registration_number,
                            registration_date = EXCLUDED.registration_date,
                            nice_classes = EXCLUDED.nice_classes,
                            us_classes = EXCLUDED.us_classes,
                            owner_name = EXCLUDED.owner_name,
                            owner_entity_type = EXCLUDED.owner_entity_type,
                            goods_and_services = EXCLUDED.goods_and_services,
                            description_of_mark = EXCLUDED.description_of_mark,
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash,
                            _loaded_at = NOW()
                        """,
                        (
                            record.serial_number,
                            record.mark_element,
                            record.mark_type,
                            record.status,
                            record.status_code,
                            record.status_date,
                            record.filing_date,
                            record.registration_number,
                            record.registration_date,
                            record.nice_classes,
                            record.us_classes,
                            record.owner_name,
                            record.owner_entity_type,
                            record.goods_and_services,
                            record.description_of_mark,
                            source_file or "tsdr_api",
                            source_hash,
                        ),
                    )
                    records_inserted += 1

                    # Track status changes
                    _track_status_change(
                        cur, record.serial_number, "uspto_trademarks", record.status
                    )

                    if records_inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("Committed batch: %d records so far", records_inserted)

                        try:
                            from dk_data.observability.metrics import record_data_source_refresh
                            record_data_source_refresh("uspto_trademarks", "uspto_trademarks", records_inserted)
                        except Exception:
                            pass

                except ValidationError as e:
                    records_failed += 1
                    errors.append({"index": idx, "error": str(e), "type": "validation"})
                    if records_failed <= 5:
                        logger.warning("Validation error at index %d: %s", idx, e)

                except Exception as e:
                    records_failed += 1
                    errors.append({"index": idx, "error": str(e), "type": "database"})
                    logger.error("Database error at index %d: %s", idx, e)

            # Final commit
            conn.commit()

    try:
        from dk_data.observability.metrics import record_data_source_refresh
        record_data_source_refresh("uspto_trademarks", "uspto_trademarks", records_inserted)
    except Exception:
        pass

    logger.info(
        "USPTO trademark load complete: %d inserted, %d failed",
        records_inserted, records_failed,
    )

    return {
        "status": "success" if records_inserted > 0 or records_failed == 0 else "failed",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10],
    }


def _parse_date(value: Any) -> Optional[date]:
    """Best-effort parsing of a date value from TSDR.

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
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m", "%Y"):
            try:
                return datetime.strptime(value[: len(fmt.replace("%", "0"))], fmt).date()
            except (ValueError, IndexError):
                continue
        try:
            return datetime.fromisoformat(value).date()
        except (ValueError, TypeError):
            pass
    return None


def _track_status_change(
    cur,
    trademark_identifier: str,
    source: str,
    new_status: Optional[str],
) -> None:
    """Compare status with last known and insert history row if changed.

    Error handling: history INSERT failure must not block the main upsert.
    """
    if not new_status:
        return

    try:
        cur.execute(
            """
            SELECT new_status FROM ip_raw.trademark_status_history
            WHERE trademark_identifier = %s AND source = %s
            ORDER BY changed_at DESC
            LIMIT 1
            """,
            (trademark_identifier, source),
        )
        row = cur.fetchone()
        old_status = row[0] if row else None

        if old_status != new_status:
            cur.execute(
                """
                INSERT INTO ip_raw.trademark_status_history
                    (trademark_identifier, source, old_status, new_status)
                VALUES (%s, %s, %s, %s)
                """,
                (trademark_identifier, source, old_status, new_status),
            )
    except Exception as e:
        logger.warning(
            "Failed to track status change for %s/%s: %s",
            trademark_identifier, source, e,
        )
