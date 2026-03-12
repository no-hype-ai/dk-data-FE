"""Source loader for CMS Part B Drug Spending."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsPartBSpendingRecord(BaseModel):
    """Validated record for CMS Part B drug spending data."""

    hcpcs_code: str
    brand_name: Optional[str] = None
    generic_name: Optional[str] = None
    total_spending: Optional[float] = None
    total_claims: Optional[int] = None
    total_beneficiaries: Optional[int] = None
    year: Optional[str] = None

    @field_validator("hcpcs_code")
    @classmethod
    def hcpcs_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("hcpcs_code must not be empty")
        return v


def load_cms_part_b_spending_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS Part B spending records into raw.cms_part_b_spending."""
    validated: List[CmsPartBSpendingRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsPartBSpendingRecord(**rec))
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
                        r.hcpcs_code,
                        r.brand_name,
                        r.generic_name,
                        r.total_spending,
                        r.total_claims,
                        r.total_beneficiaries,
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
                    INSERT INTO raw.cms_part_b_spending (
                        hcpcs_code, brand_name, generic_name, total_spending,
                        total_claims, total_beneficiaries, year,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (hcpcs_code, year) DO UPDATE SET
                        brand_name = EXCLUDED.brand_name,
                        generic_name = EXCLUDED.generic_name,
                        total_spending = EXCLUDED.total_spending,
                        total_claims = EXCLUDED.total_claims,
                        total_beneficiaries = EXCLUDED.total_beneficiaries,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_part_b_spending: inserted batch %d–%d of %d",
                    start, start + len(batch), len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_part_b_spending: batch insert failed")
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
