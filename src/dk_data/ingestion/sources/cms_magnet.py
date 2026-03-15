"""Source loader for CMS Magnet designation data."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsMagnetRecord(BaseModel):
    """Validated record for CMS Magnet designation data."""

    facility_name: str
    city: Optional[str] = None
    state: str
    country: Optional[str] = None
    zip_code: Optional[str] = None
    designation_year: Optional[str] = None
    redesignation_years: Optional[str] = None
    web_address: Optional[str] = None

    @field_validator("facility_name")
    @classmethod
    def facility_name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("facility_name must not be empty")
        return v

    @field_validator("state")
    @classmethod
    def state_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("state must not be empty")
        return v


def load_cms_magnet_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS Magnet records into raw.cms_magnet."""
    validated: List[CmsMagnetRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsMagnetRecord(**rec))
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
                        r.facility_name,
                        r.city,
                        r.state,
                        r.country,
                        r.zip_code,
                        r.designation_year,
                        r.redesignation_years,
                        r.web_address,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO raw.cms_magnet (
                        facility_name, city, state, country, zip_code,
                        designation_year, redesignation_years, web_address,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (facility_name, state) DO UPDATE SET
                        city = EXCLUDED.city,
                        country = EXCLUDED.country,
                        zip_code = EXCLUDED.zip_code,
                        designation_year = EXCLUDED.designation_year,
                        redesignation_years = EXCLUDED.redesignation_years,
                        web_address = EXCLUDED.web_address,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_magnet: inserted batch %d–%d of %d",
                    start,
                    start + len(batch),
                    len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_magnet: batch insert failed")
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
