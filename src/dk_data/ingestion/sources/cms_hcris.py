"""Source loader for CMS HCRIS (Hospital Cost Report Information System) data."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsHcrisRecord(BaseModel):
    """Validated record for CMS HCRIS data."""

    ccn: str
    fiscal_year_begin: Optional[str] = None
    fiscal_year_end: Optional[str] = None
    worksheet: str
    line_number: str
    column_number: str
    value: Optional[str] = None

    @field_validator("ccn")
    @classmethod
    def ccn_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("ccn must not be empty")
        return v

    @field_validator("worksheet")
    @classmethod
    def worksheet_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("worksheet must not be empty")
        return v

    @field_validator("line_number")
    @classmethod
    def line_number_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("line_number must not be empty")
        return v

    @field_validator("column_number")
    @classmethod
    def column_number_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("column_number must not be empty")
        return v


def load_cms_hcris_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS HCRIS records into raw.cms_hcris.

    Args:
        records: List of dicts from the fetcher.
        source_hash: Hash identifying the source snapshot.
        source_file: Original filename / URL.
        batch_size: Rows per INSERT batch.

    Returns:
        Status dict with counts and errors.
    """
    validated: List[CmsHcrisRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsHcrisRecord(**rec))
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
                        r.ccn,
                        r.fiscal_year_begin,
                        r.fiscal_year_end,
                        r.worksheet,
                        r.line_number,
                        r.column_number,
                        r.value,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO raw.cms_hcris (
                        ccn, fiscal_year_begin, fiscal_year_end, worksheet,
                        line_number, column_number, value,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (ccn, worksheet, line_number, column_number) DO UPDATE SET
                        fiscal_year_begin = EXCLUDED.fiscal_year_begin,
                        fiscal_year_end = EXCLUDED.fiscal_year_end,
                        value = EXCLUDED.value,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_hcris: inserted batch %d–%d of %d",
                    start,
                    start + len(batch),
                    len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_hcris: batch insert failed")
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
