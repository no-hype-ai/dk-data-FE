"""Source loader for CMS Outpatient PUF data."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsOutpatientPufRecord(BaseModel):
    """Validated record for CMS Outpatient PUF data."""

    ccn: str  # mapped to DB column provider_id
    hcpcs_code: str  # mapped to DB column apc_code
    hcpcs_description: Optional[str] = None  # accepted from fetcher, not in DB
    total_services: Optional[int] = None
    avg_est_submitted_charges: Optional[float] = None  # mapped to DB column avg_estimated_payment
    avg_total_payments: Optional[float] = None
    year: Optional[int] = None

    @field_validator("ccn")
    @classmethod
    def ccn_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("ccn must not be empty")
        return v

    @field_validator("hcpcs_code")
    @classmethod
    def hcpcs_code_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("hcpcs_code must not be empty")
        return v

    @field_validator("total_services", mode="before")
    @classmethod
    def coerce_total_services(cls, v):
        if v is None or v == "":
            return None
        return int(v)

    @field_validator("avg_est_submitted_charges", "avg_total_payments", mode="before")
    @classmethod
    def coerce_float(cls, v):
        if v is None or v == "":
            return None
        return float(v)


def load_cms_outpatient_puf_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS Outpatient PUF records into raw.cms_outpatient_puf.

    Args:
        records: List of dicts from the fetcher.
        source_hash: Hash identifying the source snapshot.
        source_file: Original filename / URL.
        batch_size: Rows per INSERT batch.

    Returns:
        Status dict with counts and errors.
    """
    validated: List[CmsOutpatientPufRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsOutpatientPufRecord(**rec))
        except Exception as exc:
            errors.append({"row": idx, "error": str(exc)})

    if not validated:
        return {
            "status": "partial" if errors else "success",
            "records_inserted": 0,
            "records_failed": len(errors),
            "errors": errors[:50],
        }

    # Filter out records with null PK fields — the DB requires (provider_id, apc_code, year)
    before_count = len(validated)
    validated = [r for r in validated if r.year is not None]
    skipped_null_pk = before_count - len(validated)
    if skipped_null_pk:
        logger.info(
            "cms_outpatient_puf: skipped %d records with null PK field (year)",
            skipped_null_pk,
        )

    if not validated:
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": len(errors),
            "records_skipped_null_pk": skipped_null_pk,
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
                        r.ccn,
                        r.hcpcs_code,
                        r.total_services,
                        r.avg_est_submitted_charges,
                        r.avg_total_payments,
                        r.year,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO raw.cms_outpatient_puf (
                        provider_id, apc_code, total_services,
                        avg_estimated_payment, avg_total_payments,
                        year, _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (provider_id, apc_code, year) DO UPDATE SET
                        total_services = EXCLUDED.total_services,
                        avg_estimated_payment = EXCLUDED.avg_estimated_payment,
                        avg_total_payments = EXCLUDED.avg_total_payments,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_outpatient_puf: inserted batch %d–%d of %d",
                    start,
                    start + len(batch),
                    len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_outpatient_puf: batch insert failed")
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
