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
    """Validated record for USP drug classification alignment data."""

    rxcui: str
    tty: Optional[str] = None
    branded_name: Optional[str] = None
    related_bn: Optional[str] = None
    related_df: Optional[str] = None
    usp_category: str
    usp_class: str

    @field_validator("rxcui")
    @classmethod
    def rxcui_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("rxcui must not be empty")
        return v

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
    """Load CMS USP alignment records into hcs_raw.cms_usp."""
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

    # Deduplicate by PK (rxcui, usp_category, usp_class)
    seen: set = set()
    deduped: List[CmsUspRecord] = []
    for r in validated:
        key = (r.rxcui, r.usp_category, r.usp_class)
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    validated = deduped

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
                        r.rxcui,
                        r.tty,
                        r.branded_name,
                        r.related_bn,
                        r.related_df,
                        r.usp_category,
                        r.usp_class,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO hcs_raw.cms_usp (
                        rxcui, tty, branded_name, related_bn, related_df,
                        usp_category, usp_class,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (rxcui, usp_category, usp_class) DO UPDATE SET
                        tty = EXCLUDED.tty,
                        branded_name = EXCLUDED.branded_name,
                        related_bn = EXCLUDED.related_bn,
                        related_df = EXCLUDED.related_df,
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
