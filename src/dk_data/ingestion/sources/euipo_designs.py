"""EUIPO Design Data Loader.

Feature: 014-uspto-euipo-model-datasource
Loads EUIPO registered community design records into ip_raw.euipo_designs
with upsert semantics (ON CONFLICT DO UPDATE on application_number).

Target table: ip_raw.euipo_designs
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import EUIPODesignRecord

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def load_euipo_designs_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load EUIPO design records into ip_raw.euipo_designs.

    Args:
        records: List of normalised design dicts from EUIPODesignsFetcher.
        source_hash: Optional content hash for lineage tracking.
        source_file: Optional source file identifier.
        batch_size: Number of records to commit at once.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("No EUIPO design records to load")
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info("Loading %d EUIPO design records into ip_raw.euipo_designs", len(records))

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    for date_field in ("filing_date", "registration_date", "expiry_date", "publication_date"):
                        raw_record[date_field] = _parse_date(raw_record.get(date_field))

                    record = EUIPODesignRecord(**raw_record)

                    cur.execute(
                        """
                        INSERT INTO ip_raw.euipo_designs (
                            application_number, design_title,
                            applicant_name, applicant_country,
                            representative_name, designer_name,
                            status, filing_date, registration_date,
                            expiry_date, publication_date,
                            locarno_classes, product_indication,
                            image_url, number_of_designs,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s
                        )
                        ON CONFLICT (application_number) DO UPDATE SET
                            design_title = EXCLUDED.design_title,
                            applicant_name = EXCLUDED.applicant_name,
                            applicant_country = EXCLUDED.applicant_country,
                            representative_name = EXCLUDED.representative_name,
                            designer_name = EXCLUDED.designer_name,
                            status = EXCLUDED.status,
                            filing_date = EXCLUDED.filing_date,
                            registration_date = EXCLUDED.registration_date,
                            expiry_date = EXCLUDED.expiry_date,
                            publication_date = EXCLUDED.publication_date,
                            locarno_classes = EXCLUDED.locarno_classes,
                            product_indication = EXCLUDED.product_indication,
                            image_url = EXCLUDED.image_url,
                            number_of_designs = EXCLUDED.number_of_designs,
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash,
                            _loaded_at = NOW()
                        """,
                        (
                            record.application_number,
                            record.design_title,
                            record.applicant_name,
                            record.applicant_country,
                            record.representative_name,
                            record.designer_name,
                            record.status,
                            record.filing_date,
                            record.registration_date,
                            record.expiry_date,
                            record.publication_date,
                            record.locarno_classes,
                            record.product_indication,
                            record.image_url,
                            record.number_of_designs,
                            source_file or "euipo_designs",
                            source_hash,
                        ),
                    )
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("Committed batch: %d records so far", records_inserted)

                except ValidationError as e:
                    records_failed += 1
                    errors.append({"index": idx, "error": str(e), "type": "validation"})
                    if records_failed <= 5:
                        logger.warning("Validation error at index %d: %s", idx, e)

                except Exception as e:
                    records_failed += 1
                    errors.append({"index": idx, "error": str(e), "type": "database"})
                    logger.error("Database error at index %d: %s", idx, e)

            conn.commit()

    logger.info(
        "EUIPO design load complete: %d inserted, %d failed",
        records_inserted, records_failed,
    )

    return {
        "status": "success" if records_inserted > 0 or records_failed == 0 else "failed",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10],
    }


def _parse_date(value: Any) -> Optional[date]:
    """Best-effort parsing of a date value from EUIPO."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m", "%Y"):
            try:
                return datetime.strptime(value[: len(fmt.replace("%", "0"))], fmt).date()
            except (ValueError, IndexError):
                continue
        try:
            return datetime.fromisoformat(value).date()
        except (ValueError, TypeError):
            pass
    return None
