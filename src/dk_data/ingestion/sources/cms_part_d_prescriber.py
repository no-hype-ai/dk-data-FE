"""Source loader for CMS Part D Prescriber data."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsPartDPrescriberRecord(BaseModel):
    """Validated record for CMS Part D Prescriber data."""

    npi: str
    prescriber_last_org_name: Optional[str] = None
    prescriber_first_name: Optional[str] = None
    prescriber_city: Optional[str] = None
    prescriber_state: Optional[str] = None
    prescriber_type: Optional[str] = None
    drug_brand_name: str
    drug_generic_name: Optional[str] = None
    total_claims: Optional[float] = None
    total_30day_fills: Optional[float] = None
    total_drug_cost: Optional[float] = None
    total_beneficiaries: Optional[int] = None
    year: int

    @field_validator("npi")
    @classmethod
    def npi_must_be_10_digits(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or len(v) != 10:
            raise ValueError(f"NPI must be exactly 10 digits, got '{v}'")
        return v

    @field_validator("year")
    @classmethod
    def year_reasonable(cls, v: int) -> int:
        if v < 2000 or v > 2099:
            raise ValueError(f"Year out of expected range: {v}")
        return v


def load_cms_part_d_prescriber_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS Part D Prescriber records into raw.cms_part_d_prescriber.

    Args:
        records: List of dicts from the fetcher.
        source_hash: Hash identifying the source snapshot.
        source_file: Original filename / URL.
        batch_size: Rows per INSERT batch.

    Returns:
        Status dict with counts and errors.
    """
    validated: List[CmsPartDPrescriberRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsPartDPrescriberRecord(**rec))
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
                        r.prescriber_last_org_name,
                        r.prescriber_first_name,
                        r.prescriber_city,
                        r.prescriber_state,
                        r.prescriber_type,
                        r.drug_brand_name,
                        r.drug_generic_name,
                        r.total_claims,
                        r.total_30day_fills,
                        r.total_drug_cost,
                        r.total_beneficiaries,
                        r.year,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO raw.cms_part_d_prescriber (
                        npi, prescriber_last_org_name, prescriber_first_name,
                        prescriber_city, prescriber_state, prescriber_type,
                        drug_brand_name, drug_generic_name,
                        total_claims, total_30day_fills, total_drug_cost,
                        total_beneficiaries, year,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (npi, drug_brand_name, year) DO UPDATE SET
                        prescriber_last_org_name = EXCLUDED.prescriber_last_org_name,
                        prescriber_first_name = EXCLUDED.prescriber_first_name,
                        prescriber_city = EXCLUDED.prescriber_city,
                        prescriber_state = EXCLUDED.prescriber_state,
                        prescriber_type = EXCLUDED.prescriber_type,
                        drug_generic_name = EXCLUDED.drug_generic_name,
                        total_claims = EXCLUDED.total_claims,
                        total_30day_fills = EXCLUDED.total_30day_fills,
                        total_drug_cost = EXCLUDED.total_drug_cost,
                        total_beneficiaries = EXCLUDED.total_beneficiaries,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_part_d_prescriber: inserted batch %d–%d of %d",
                    start,
                    start + len(batch),
                    len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_part_d_prescriber: batch insert failed")
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
