"""Source loader for CMS Provider of Services (POS) data."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsPosRecord(BaseModel):
    """Validated record for CMS Provider of Services data."""

    ccn: str
    facility_name: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    provider_type: Optional[str] = None
    beds: Optional[int] = None
    ownership_type: Optional[str] = None

    @field_validator("ccn")
    @classmethod
    def ccn_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("ccn must not be empty")
        return v

    @field_validator("beds", mode="before")
    @classmethod
    def coerce_beds(cls, v):
        if v is None or v == "":
            return None
        return int(v)


def load_cms_pos_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS POS records into raw.cms_pos.

    Args:
        records: List of dicts from the fetcher.
        source_hash: Hash identifying the source snapshot.
        source_file: Original filename / URL.
        batch_size: Rows per INSERT batch.

    Returns:
        Status dict with counts and errors.
    """
    validated: List[CmsPosRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsPosRecord(**rec))
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
                        r.facility_name,
                        r.street_address,
                        r.city,
                        r.state,
                        r.zip_code,
                        r.provider_type,
                        r.beds,
                        r.ownership_type,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO raw.cms_pos (
                        ccn, facility_name, street_address, city, state,
                        zip_code, provider_type, beds, ownership_type,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (ccn) DO UPDATE SET
                        facility_name = EXCLUDED.facility_name,
                        street_address = EXCLUDED.street_address,
                        city = EXCLUDED.city,
                        state = EXCLUDED.state,
                        zip_code = EXCLUDED.zip_code,
                        provider_type = EXCLUDED.provider_type,
                        beds = EXCLUDED.beds,
                        ownership_type = EXCLUDED.ownership_type,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_pos: inserted batch %d–%d of %d",
                    start,
                    start + len(batch),
                    len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_pos: batch insert failed")
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
