"""Source loader for CMS Part D Drug Spending."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CmsPartDSpendingRecord(BaseModel):
    """Validated record for CMS Part D drug spending data."""

    brand_name: Optional[str] = None
    generic_name: Optional[str] = None
    total_spending: Optional[float] = None
    total_claims: Optional[int] = None
    total_beneficiaries: Optional[int] = None
    avg_cost_per_claim: Optional[float] = None
    year: Optional[str] = None


def load_cms_part_d_spending_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS Part D spending records into raw.cms_part_d_spending."""
    validated: List[CmsPartDSpendingRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsPartDSpendingRecord(**rec))
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
                        r.brand_name,
                        r.generic_name,
                        r.total_spending,
                        r.total_claims,
                        r.total_beneficiaries,
                        r.avg_cost_per_claim,
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
                    INSERT INTO raw.cms_part_d_spending (
                        brand_name, generic_name, total_spending, total_claims,
                        total_beneficiaries, avg_cost_per_claim, year,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (brand_name, year) DO UPDATE SET
                        generic_name = EXCLUDED.generic_name,
                        total_spending = EXCLUDED.total_spending,
                        total_claims = EXCLUDED.total_claims,
                        total_beneficiaries = EXCLUDED.total_beneficiaries,
                        avg_cost_per_claim = EXCLUDED.avg_cost_per_claim,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_part_d_spending: inserted batch %d–%d of %d",
                    start, start + len(batch), len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_part_d_spending: batch insert failed")
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
