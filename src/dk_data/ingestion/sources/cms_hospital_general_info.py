"""Source loader for CMS Hospital General Information data."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsHospitalGeneralInfoRecord(BaseModel):
    """Validated record for CMS Hospital General Information data."""

    facility_id: str
    facility_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    county_name: Optional[str] = None
    phone_number: Optional[str] = None
    hospital_type: Optional[str] = None
    hospital_ownership: Optional[str] = None
    emergency_services: Optional[str] = None

    @field_validator("facility_id")
    @classmethod
    def facility_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("facility_id must not be empty")
        return v


def load_cms_hospital_general_info_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS Hospital General Info records into hcs_raw.cms_hospital_general_info.

    Args:
        records: List of dicts from the fetcher.
        source_hash: Hash identifying the source snapshot.
        source_file: Original filename / URL.
        batch_size: Rows per INSERT batch.

    Returns:
        Status dict with counts and errors.
    """
    validated: List[CmsHospitalGeneralInfoRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsHospitalGeneralInfoRecord(**rec))
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
                        r.facility_id,
                        r.facility_name,
                        r.address,
                        r.city,
                        r.state,
                        r.zip_code,
                        r.county_name,
                        r.phone_number,
                        r.hospital_type,
                        r.hospital_ownership,
                        r.emergency_services,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO hcs_raw.cms_hospital_general_info (
                        facility_id, facility_name, address, city, state,
                        zip_code, county_name, phone_number, hospital_type,
                        hospital_ownership, emergency_services,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (facility_id) DO UPDATE SET
                        facility_name = EXCLUDED.facility_name,
                        address = EXCLUDED.address,
                        city = EXCLUDED.city,
                        state = EXCLUDED.state,
                        zip_code = EXCLUDED.zip_code,
                        county_name = EXCLUDED.county_name,
                        phone_number = EXCLUDED.phone_number,
                        hospital_type = EXCLUDED.hospital_type,
                        hospital_ownership = EXCLUDED.hospital_ownership,
                        emergency_services = EXCLUDED.emergency_services,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_hospital_general_info: inserted batch %d–%d of %d",
                    start,
                    start + len(batch),
                    len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_hospital_general_info: batch insert failed")
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
