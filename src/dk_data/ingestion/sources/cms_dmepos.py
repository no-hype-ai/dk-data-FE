"""Source loader for CMS DMEPOS Utilization."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsDmeposRecord(BaseModel):
    """Validated record for CMS DMEPOS utilization data."""

    npi: str
    hcpcs_code: Optional[str] = None
    hcpcs_description: Optional[str] = None
    total_services: Optional[int] = None
    total_beneficiaries: Optional[int] = None
    avg_submitted_charge: Optional[float] = None
    avg_medicare_payment: Optional[float] = None

    @field_validator("npi")
    @classmethod
    def npi_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("npi must not be empty")
        return v


def load_cms_dmepos_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS DMEPOS records into raw.cms_dmepos."""
    validated: List[CmsDmeposRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsDmeposRecord(**rec))
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
                        r.npi,
                        r.hcpcs_code,
                        r.hcpcs_description,
                        r.total_services,
                        r.total_beneficiaries,
                        r.avg_submitted_charge,
                        r.avg_medicare_payment,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO raw.cms_dmepos (
                        npi, hcpcs_code, hcpcs_description, total_services,
                        total_beneficiaries, avg_submitted_charge, avg_medicare_payment,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (npi, hcpcs_code) DO UPDATE SET
                        hcpcs_description = EXCLUDED.hcpcs_description,
                        total_services = EXCLUDED.total_services,
                        total_beneficiaries = EXCLUDED.total_beneficiaries,
                        avg_submitted_charge = EXCLUDED.avg_submitted_charge,
                        avg_medicare_payment = EXCLUDED.avg_medicare_payment,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_dmepos: inserted batch %d–%d of %d",
                    start, start + len(batch), len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_dmepos: batch insert failed")
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
