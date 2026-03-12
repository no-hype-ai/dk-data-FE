"""Source loader for CMS USP (United States Pharmacopeia) Drug Classification."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsUspRecord(BaseModel):
    """Validated record for USP drug classification data."""

    usp_category: str
    usp_class: str
    drug_names: Optional[str] = None

    @field_validator("usp_category")
    @classmethod
    def category_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("usp_category must not be empty")
        return v

    @field_validator("usp_class")
    @classmethod
    def class_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("usp_class must not be empty")
        return v


def load_cms_usp_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS USP records into raw.cms_usp."""
    validated: List[CmsUspRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsUspRecord(**rec))
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
                        r.usp_category,
                        r.usp_class,
                        r.drug_names,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO raw.cms_usp (
                        usp_category, usp_class, drug_names,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (usp_category, usp_class) DO UPDATE SET
                        drug_names = EXCLUDED.drug_names,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_usp: inserted batch %d–%d of %d",
                    start, start + len(batch), len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_usp: batch insert failed")
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
