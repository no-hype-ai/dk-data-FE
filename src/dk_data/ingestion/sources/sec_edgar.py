"""SEC EDGAR Filings Data Loader.

Feature: 011-datasource-integration
Task: T070-T072 — SEC EDGAR pharmaceutical filings

Loads normalised SEC EDGAR filing records into raw.sec_edgar with
upsert semantics (ON CONFLICT DO UPDATE on accession_number).

Target table: raw.sec_edgar (see migration 060_ci_source_tables.sql)
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import SECEdgarRecord

logger = logging.getLogger(__name__)

# Batch commit interval
BATCH_SIZE = 500


def load_sec_edgar_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load SEC EDGAR filing records into raw.sec_edgar.

    Validates each record using Pydantic and performs an upsert:
    INSERT ... ON CONFLICT (accession_number) DO UPDATE.

    Args:
        records: List of normalised filing record dicts from SECEdgarFetcher.
        source_hash: Optional content hash for lineage tracking.
        source_file: Optional source file identifier.
        batch_size: Number of records to commit at once.

    Returns:
        Dict with status, records_inserted, records_failed, errors.
    """
    if not records:
        logger.warning("No SEC EDGAR records to load")
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": 0,
            "errors": [],
        }

    logger.info("Loading %d SEC EDGAR records into raw.sec_edgar", len(records))

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    # Validate with Pydantic
                    record = SECEdgarRecord(**raw_record)

                    cur.execute(
                        """
                        INSERT INTO raw.sec_edgar (
                            accession_number, company_name, cik,
                            filing_type, filing_date,
                            document_url, description,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s
                        )
                        ON CONFLICT (accession_number) DO UPDATE SET
                            company_name = EXCLUDED.company_name,
                            cik = EXCLUDED.cik,
                            filing_type = EXCLUDED.filing_type,
                            filing_date = EXCLUDED.filing_date,
                            document_url = EXCLUDED.document_url,
                            description = EXCLUDED.description,
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash,
                            _loaded_at = NOW()
                        """,
                        (
                            record.accession_number,
                            record.company_name,
                            record.cik,
                            record.filing_type,
                            record.filing_date,
                            record.document_url,
                            record.description,
                            source_file or "sec_edgar_api",
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

            # Final commit
            conn.commit()

    logger.info(
        "SEC EDGAR load complete: %d inserted, %d failed",
        records_inserted, records_failed,
    )

    return {
        "status": "success" if records_inserted > 0 or records_failed == 0 else "failed",
        "records_inserted": records_inserted,
        "records_failed": records_failed,
        "errors": errors[:10],
    }
