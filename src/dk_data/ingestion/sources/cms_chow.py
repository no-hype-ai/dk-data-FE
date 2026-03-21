"""Source loader for CMS Change of Ownership (CHOW) data."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsChowRecord(BaseModel):
    """Validated record for CMS Change of Ownership data."""

    ccn: str
    previous_owner: Optional[str] = None
    new_owner: Optional[str] = None
    effective_date: Optional[str] = None
    provider_type: Optional[str] = None

    @field_validator("ccn")
    @classmethod
    def ccn_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("ccn must not be empty")
        return v

    @property
    def chow_id(self) -> str:
        """Derive a synthetic PK from ccn + effective_date."""
        return f"{self.ccn}_{self.effective_date or 'unknown'}"

    @property
    def old_owner(self) -> Optional[str]:
        """Map fetcher field 'previous_owner' to DB column 'old_owner'."""
        return self.previous_owner


def load_cms_chow_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS CHOW records into hcs_raw.cms_chow.

    Args:
        records: List of dicts from the fetcher.
        source_hash: Hash identifying the source snapshot.
        source_file: Original filename / URL.
        batch_size: Rows per INSERT batch.

    Returns:
        Status dict with counts and errors.
    """
    validated: List[CmsChowRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsChowRecord(**rec))
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
                        r.chow_id,
                        r.ccn,
                        r.old_owner,
                        r.new_owner,
                        r.effective_date,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO hcs_raw.cms_chow (
                        chow_id, ccn, old_owner, new_owner, effective_date,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (chow_id) DO UPDATE SET
                        ccn = EXCLUDED.ccn,
                        old_owner = EXCLUDED.old_owner,
                        new_owner = EXCLUDED.new_owner,
                        effective_date = EXCLUDED.effective_date,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_chow: inserted batch %d–%d of %d",
                    start,
                    start + len(batch),
                    len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_chow: batch insert failed")
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
