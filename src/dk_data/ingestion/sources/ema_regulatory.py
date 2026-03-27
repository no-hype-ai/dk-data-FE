"""EMA Regulatory CI Data Loader.

Feature: 011-datasource-integration
Task: Tier 4 CI source — EMA regulatory decisions

Loads normalised EMA regulatory records (CHMP opinions, EPAR documents,
safety signals) into raw.ema_regulatory.

Target table: raw.ema_regulatory (see migration 060_ci_source_tables.sql)
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import EMARegulatoryCIRecord

logger = logging.getLogger(__name__)


def load_ema_regulatory_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Load EMA regulatory records into raw.ema_regulatory.

    Uses INSERT ... ON CONFLICT (document_id) DO UPDATE so that re-runs
    will refresh existing rows with the latest data.

    Args:
        records: List of normalised record dicts as returned by the fetcher.
        source_hash: Optional SHA-256 hash of the fetch payload.

    Returns:
        Dictionary with:
        - status: 'success' or 'failed'
        - records_inserted: Number of rows upserted
        - records_failed: Number of rows that failed validation
        - errors: First 10 error details
    """
    if not records:
        logger.warning("No EMA regulatory records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info("Loading %d EMA regulatory records", len(records))

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    # Validate through Pydantic model
                    record = EMARegulatoryCIRecord(
                        document_id=raw_record["document_id"],
                        document_type=raw_record.get("document_type"),
                        product_name=raw_record.get("product_name"),
                        active_substance=raw_record.get("active_substance"),
                        therapeutic_area=raw_record.get("therapeutic_area"),
                        decision_date=raw_record.get("decision_date"),
                        decision_type=raw_record.get("decision_type"),
                        document_url=raw_record.get("document_url"),
                        summary=raw_record.get("summary"),
                    )

                    cur.execute(
                        """
                        INSERT INTO raw.ema_regulatory (
                            document_id,
                            document_type,
                            product_name,
                            active_substance,
                            therapeutic_area,
                            decision_date,
                            decision_type,
                            document_url,
                            summary,
                            _source_file,
                            _source_hash
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (document_id) DO UPDATE SET
                            document_type   = EXCLUDED.document_type,
                            product_name    = EXCLUDED.product_name,
                            active_substance = EXCLUDED.active_substance,
                            therapeutic_area = EXCLUDED.therapeutic_area,
                            decision_date   = EXCLUDED.decision_date,
                            decision_type   = EXCLUDED.decision_type,
                            document_url    = EXCLUDED.document_url,
                            summary         = EXCLUDED.summary,
                            _source_file    = EXCLUDED._source_file,
                            _source_hash    = EXCLUDED._source_hash,
                            _loaded_at      = NOW()
                        """,
                        (
                            record.document_id,
                            record.document_type,
                            record.product_name,
                            record.active_substance,
                            record.therapeutic_area,
                            record.decision_date,
                            record.decision_type,
                            record.document_url,
                            record.summary,
                            "ema_regulatory_api",
                            source_hash,
                        ),
                    )
                    records_inserted += 1

                except ValidationError as e:
                    records_failed += 1
                    errors.append({"index": idx, "error": str(e)})
                    if records_failed <= 5:
                        logger.warning(
                            "Validation error at index %d: %s", idx, e
                        )

                except Exception as e:
                    records_failed += 1
                    errors.append({"index": idx, "error": str(e)})
                    logger.error("Error at index %d: %s", idx, e)

            conn.commit()

    logger.info(
        "EMA regulatory load complete: %d inserted, %d failed",
        records_inserted,
        records_failed,
    )

    return {
        "status": "success",
        "records_fetched": len(records),
        "records_inserted": records_inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
