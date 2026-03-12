"""Source loader for CMS Open Payments data."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsOpenPaymentRecord(BaseModel):
    """Validated record for CMS Open Payments data."""

    record_id: str
    payment_type: Optional[str] = None
    covered_recipient_npi: Optional[str] = None
    manufacturer_name: Optional[str] = None
    total_amount_usd: Optional[float] = None
    date_of_payment: Optional[str] = None
    nature_of_payment: Optional[str] = None
    form_of_payment: Optional[str] = None

    @field_validator("record_id")
    @classmethod
    def record_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("record_id must not be empty")
        return v

    @field_validator("covered_recipient_npi")
    @classmethod
    def npi_format_if_present(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if v and (not v.isdigit() or len(v) != 10):
            raise ValueError(f"NPI must be exactly 10 digits, got '{v}'")
        return v or None


def load_cms_open_payments_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS Open Payments records into raw.cms_open_payments.

    Args:
        records: List of dicts from the fetcher.
        source_hash: Hash identifying the source snapshot.
        source_file: Original filename / URL.
        batch_size: Rows per INSERT batch.

    Returns:
        Status dict with counts and errors.
    """
    validated: List[CmsOpenPaymentRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsOpenPaymentRecord(**rec))
        except Exception as exc:
            errors.append({"row": idx, "error": str(exc)})

    if not validated:
        return {
            "status": "partial" if errors else "success",
            "records_inserted": 0,
            "records_failed": len(errors),
            "errors": errors[:50],
        }

    loaded_at = datetime.utcnow()

    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        database=os.getenv("POSTGRES_DB", "dk_data"),
    )

    records_inserted = 0
    try:
        with conn.cursor() as cur:
            for start in range(0, len(validated), batch_size):
                batch = validated[start : start + batch_size]
                values = [
                    (
                        r.record_id,
                        r.payment_type,
                        r.covered_recipient_npi,
                        r.manufacturer_name,
                        r.total_amount_usd,
                        r.date_of_payment,
                        r.nature_of_payment,
                        r.form_of_payment,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO raw.cms_open_payments (
                        record_id, payment_type, covered_recipient_npi,
                        manufacturer_name, total_amount_usd, date_of_payment,
                        nature_of_payment, form_of_payment,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (record_id) DO UPDATE SET
                        payment_type = EXCLUDED.payment_type,
                        covered_recipient_npi = EXCLUDED.covered_recipient_npi,
                        manufacturer_name = EXCLUDED.manufacturer_name,
                        total_amount_usd = EXCLUDED.total_amount_usd,
                        date_of_payment = EXCLUDED.date_of_payment,
                        nature_of_payment = EXCLUDED.nature_of_payment,
                        form_of_payment = EXCLUDED.form_of_payment,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_open_payments: inserted batch %d–%d of %d",
                    start,
                    start + len(batch),
                    len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_open_payments: batch insert failed")
        errors.append({"row": "batch", "error": str(exc)})
    finally:
        conn.close()

    status = "success" if not errors else "partial"
    return {
        "status": status,
        "records_inserted": records_inserted,
        "records_failed": len(errors),
        "errors": errors[:50],
    }
