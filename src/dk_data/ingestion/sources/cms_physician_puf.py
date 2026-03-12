"""Source loader for CMS Physician and Other Practitioners Public Use File (PUF)."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsPhysicianPufRecord(BaseModel):
    """Validated record for CMS Physician PUF data."""

    npi: str
    provider_last_org_name: Optional[str] = None
    provider_first_name: Optional[str] = None
    provider_state: Optional[str] = None
    provider_type: Optional[str] = None
    hcpcs_code: str
    hcpcs_description: Optional[str] = None
    place_of_service: Optional[str] = None
    line_service_count: Optional[float] = None
    beneficiary_unique_count: Optional[int] = None
    avg_medicare_allowed_amt: Optional[float] = None
    avg_submitted_charge_amt: Optional[float] = None
    avg_medicare_payment_amt: Optional[float] = None
    year: int

    @field_validator("npi")
    @classmethod
    def npi_must_be_10_digits(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or len(v) != 10:
            raise ValueError(f"NPI must be exactly 10 digits, got '{v}'")
        return v

    @field_validator("year")
    @classmethod
    def year_reasonable(cls, v: int) -> int:
        if v < 2000 or v > 2099:
            raise ValueError(f"Year out of expected range: {v}")
        return v


def load_cms_physician_puf_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS Physician PUF records into raw.cms_physician_puf.

    Args:
        records: List of dicts from the fetcher.
        source_hash: Hash identifying the source snapshot.
        source_file: Original filename / URL.
        batch_size: Rows per INSERT batch.

    Returns:
        Status dict with counts and errors.
    """
    validated: List[CmsPhysicianPufRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsPhysicianPufRecord(**rec))
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
                        r.npi,
                        r.provider_last_org_name,
                        r.provider_first_name,
                        r.provider_state,
                        r.provider_type,
                        r.hcpcs_code,
                        r.hcpcs_description,
                        r.place_of_service,
                        r.line_service_count,
                        r.beneficiary_unique_count,
                        r.avg_medicare_allowed_amt,
                        r.avg_submitted_charge_amt,
                        r.avg_medicare_payment_amt,
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
                    INSERT INTO raw.cms_physician_puf (
                        npi, provider_last_org_name, provider_first_name,
                        provider_state, provider_type,
                        hcpcs_code, hcpcs_description, place_of_service,
                        line_service_count, beneficiary_unique_count,
                        avg_medicare_allowed_amt, avg_submitted_charge_amt,
                        avg_medicare_payment_amt, year,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (npi, hcpcs_code, year) DO UPDATE SET
                        provider_last_org_name = EXCLUDED.provider_last_org_name,
                        provider_first_name = EXCLUDED.provider_first_name,
                        provider_state = EXCLUDED.provider_state,
                        provider_type = EXCLUDED.provider_type,
                        hcpcs_description = EXCLUDED.hcpcs_description,
                        place_of_service = EXCLUDED.place_of_service,
                        line_service_count = EXCLUDED.line_service_count,
                        beneficiary_unique_count = EXCLUDED.beneficiary_unique_count,
                        avg_medicare_allowed_amt = EXCLUDED.avg_medicare_allowed_amt,
                        avg_submitted_charge_amt = EXCLUDED.avg_submitted_charge_amt,
                        avg_medicare_payment_amt = EXCLUDED.avg_medicare_payment_amt,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_physician_puf: inserted batch %d–%d of %d",
                    start,
                    start + len(batch),
                    len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_physician_puf: batch insert failed")
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
