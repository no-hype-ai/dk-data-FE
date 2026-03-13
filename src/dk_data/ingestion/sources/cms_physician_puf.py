"""Source loader for CMS Physician and Other Practitioners Public Use File (PUF)."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsPhysicianPufRecord(BaseModel):
    """Validated record for CMS Physician PUF data.

    Field names match fetcher output (API_FIELD_MAP values).
    Fields not present in the DB schema are accepted but not inserted.
    """

    npi: str
    nppes_provider_last_org_name: Optional[str] = None  # not in DB
    nppes_provider_first_name: Optional[str] = None  # not in DB
    nppes_provider_state: Optional[str] = None  # not in DB
    provider_type: Optional[str] = None  # not in DB
    hcpcs_code: Optional[str] = None
    hcpcs_description: Optional[str] = None
    place_of_service: Optional[str] = None  # not in DB
    line_srvc_cnt: Optional[float] = None  # DB column: line_srvc_cnt
    bene_unique_cnt: Optional[int] = None  # DB column: bene_unique_cnt
    average_medicare_allowed_amt: Optional[float] = None  # not in DB
    average_submitted_chrg_amt: Optional[float] = None  # not in DB
    average_medicare_payment_amt: Optional[float] = None  # DB column: avg_medicare_payment_amt
    year: Optional[int] = None

    @field_validator("npi")
    @classmethod
    def npi_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("npi must not be empty")
        return v


def load_cms_physician_puf_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS Physician PUF records into raw.cms_physician_puf.

    Args:
        records: List of dicts from the fetcher.
        source_hash: Hash identifying the source snapshot.
        source_file: Original filename / URL.
        batch_size: Rows per INSERT batch.

    Returns:
        Status dict with counts and errors.
    """
    validated: List[CmsPhysicianPufRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsPhysicianPufRecord(**rec))
        except Exception as exc:
            errors.append({"row": idx, "error": str(exc)})

    if not validated:
        return {
            "status": "partial" if errors else "success",
            "records_inserted": 0,
            "records_failed": len(errors),
            "errors": errors[:50],
        }

    # Filter out records with null PK fields — the DB requires (npi, hcpcs_code, year)
    # but the API legitimately returns records without hcpcs_code or year
    before_count = len(validated)
    validated = [r for r in validated if r.hcpcs_code and r.year is not None]
    skipped_null_pk = before_count - len(validated)
    if skipped_null_pk:
        logger.info(
            "cms_physician_puf: skipped %d records with null PK fields (hcpcs_code/year)",
            skipped_null_pk,
        )

    if not validated:
        return {
            "status": "success",
            "records_inserted": 0,
            "records_failed": len(errors),
            "records_skipped_null_pk": skipped_null_pk,
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
                        r.line_srvc_cnt,
                        r.bene_unique_cnt,
                        r.average_medicare_payment_amt,
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
                    INSERT INTO raw.cms_physician_puf (
                        npi, hcpcs_code, hcpcs_description,
                        line_srvc_cnt, bene_unique_cnt,
                        avg_medicare_payment_amt, year,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (npi, hcpcs_code, year) DO UPDATE SET
                        hcpcs_description = EXCLUDED.hcpcs_description,
                        line_srvc_cnt = EXCLUDED.line_srvc_cnt,
                        bene_unique_cnt = EXCLUDED.bene_unique_cnt,
                        avg_medicare_payment_amt = EXCLUDED.avg_medicare_payment_amt,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_physician_puf: inserted batch %d–%d of %d",
                    start,
                    start + len(batch),
                    len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_physician_puf: batch insert failed")
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
