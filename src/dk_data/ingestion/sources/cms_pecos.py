"""Source loader for CMS PECOS (Provider Enrollment, Chain, and Ownership System) data."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsPecosRecord(BaseModel):
    """Validated record for CMS PECOS enrollment data."""

    enrollment_id: str
    npi: Optional[str] = None
    organization_name: Optional[str] = None
    org_npi: Optional[str] = None
    state: Optional[str] = None
    enrollment_type: Optional[str] = None
    enrollment_date: Optional[str] = None

    @field_validator("enrollment_id")
    @classmethod
    def enrollment_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("enrollment_id must not be empty")
        return v


def load_cms_pecos_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS PECOS records into raw.cms_pecos.

    Args:
        records: List of dicts from the fetcher.
        source_hash: Hash identifying the source snapshot.
        source_file: Original filename / URL.
        batch_size: Rows per INSERT batch.

    Returns:
        Status dict with counts and errors.
    """
    validated: List[CmsPecosRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsPecosRecord(**rec))
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
                        r.enrollment_id,
                        r.npi,
                        r.organization_name,
                        r.org_npi,
                        r.state,
                        r.enrollment_type,
                        r.enrollment_date,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO raw.cms_pecos (
                        enrollment_id, npi, organization_name, org_npi,
                        state, enrollment_type, enrollment_date,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (enrollment_id) DO UPDATE SET
                        npi = EXCLUDED.npi,
                        organization_name = EXCLUDED.organization_name,
                        org_npi = EXCLUDED.org_npi,
                        state = EXCLUDED.state,
                        enrollment_type = EXCLUDED.enrollment_type,
                        enrollment_date = EXCLUDED.enrollment_date,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_pecos: inserted batch %d–%d of %d",
                    start,
                    start + len(batch),
                    len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_pecos: batch insert failed")
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
