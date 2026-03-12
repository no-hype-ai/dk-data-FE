"""Source loader for CMS Chronic Conditions Prevalence."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsChronicConditionsRecord(BaseModel):
    """Validated record for CMS chronic conditions data."""

    state: str
    condition: str
    prevalence_rate: Optional[float] = None
    total_beneficiaries_with_condition: Optional[int] = None
    per_capita_spending: Optional[float] = None

    @field_validator("state")
    @classmethod
    def state_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("state must not be empty")
        return v

    @field_validator("condition")
    @classmethod
    def condition_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("condition must not be empty")
        return v


def load_cms_chronic_conditions_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS chronic conditions records into raw.cms_chronic_conditions."""
    validated: List[CmsChronicConditionsRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsChronicConditionsRecord(**rec))
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
                        r.state,
                        r.condition,
                        r.prevalence_rate,
                        r.total_beneficiaries_with_condition,
                        r.per_capita_spending,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO raw.cms_chronic_conditions (
                        state, condition, prevalence_rate,
                        total_beneficiaries_with_condition, per_capita_spending,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (state, condition) DO UPDATE SET
                        prevalence_rate = EXCLUDED.prevalence_rate,
                        total_beneficiaries_with_condition = EXCLUDED.total_beneficiaries_with_condition,
                        per_capita_spending = EXCLUDED.per_capita_spending,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_chronic_conditions: inserted batch %d–%d of %d",
                    start, start + len(batch), len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_chronic_conditions: batch insert failed")
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
