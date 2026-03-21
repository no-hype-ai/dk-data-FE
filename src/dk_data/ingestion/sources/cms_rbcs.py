"""Source loader for CMS RBCS (Restructured BETOS Classification System)."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsRbcsRecord(BaseModel):
    """Validated record for CMS RBCS classification data."""

    hcpcs_code: str
    rbcs_id: Optional[str] = None
    rbcs_category: Optional[str] = None
    rbcs_subcategory: Optional[str] = None
    rbcs_family: Optional[str] = None

    @field_validator("hcpcs_code")
    @classmethod
    def hcpcs_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("hcpcs_code must not be empty")
        return v


def load_cms_rbcs_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS RBCS records into hcs_raw.cms_rbcs."""
    validated: List[CmsRbcsRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsRbcsRecord(**rec))
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
                        r.rbcs_id,
                        r.rbcs_category,
                        r.rbcs_subcategory,
                        r.rbcs_family,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO hcs_raw.cms_rbcs (
                        hcpcs_code, rbcs_id, rbcs_category, rbcs_subcategory,
                        rbcs_family, _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (hcpcs_code) DO UPDATE SET
                        rbcs_id = EXCLUDED.rbcs_id,
                        rbcs_category = EXCLUDED.rbcs_category,
                        rbcs_subcategory = EXCLUDED.rbcs_subcategory,
                        rbcs_family = EXCLUDED.rbcs_family,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_rbcs: inserted batch %d–%d of %d",
                    start, start + len(batch), len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_rbcs: batch insert failed")
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
