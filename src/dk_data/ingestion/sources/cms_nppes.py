"""Source loader for CMS NPPES (National Plan and Provider Enumeration System)."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsNppesRecord(BaseModel):
    """Validated record for CMS NPPES provider data."""

    npi: str
    entity_type_code: Optional[str] = None
    provider_organization_name: Optional[str] = None
    provider_last_name: Optional[str] = None
    provider_first_name: Optional[str] = None
    provider_credential_text: Optional[str] = None
    provider_enumeration_date: Optional[str] = None
    provider_gender_code: Optional[str] = None
    practice_state: Optional[str] = None
    practice_zip: Optional[str] = None
    practice_phone: Optional[str] = None
    taxonomy_code_1: Optional[str] = None

    @field_validator("npi")
    @classmethod
    def npi_must_be_10_digits(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or len(v) != 10:
            raise ValueError(f"NPI must be exactly 10 digits, got '{v}'")
        return v


def load_cms_nppes_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS NPPES records into hcs_raw.cms_nppes.

    Args:
        records: List of dicts from the fetcher.
        source_hash: Hash identifying the source snapshot.
        source_file: Original filename / URL.
        batch_size: Rows per INSERT batch.

    Returns:
        Status dict with counts and errors.
    """
    validated: List[CmsNppesRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsNppesRecord(**rec))
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
                        r.entity_type_code,
                        r.provider_organization_name,
                        r.provider_last_name,
                        r.provider_first_name,
                        r.provider_credential_text,
                        r.provider_enumeration_date,
                        r.provider_gender_code,
                        r.practice_state,
                        r.practice_zip,
                        r.practice_phone,
                        r.taxonomy_code_1,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO hcs_raw.cms_nppes (
                        npi, entity_type_code, provider_organization_name,
                        provider_last_name, provider_first_name, provider_credential_text,
                        provider_enumeration_date, provider_gender_code,
                        practice_state, practice_zip, practice_phone,
                        taxonomy_code_1, _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (npi) DO UPDATE SET
                        entity_type_code = EXCLUDED.entity_type_code,
                        provider_organization_name = EXCLUDED.provider_organization_name,
                        provider_last_name = EXCLUDED.provider_last_name,
                        provider_first_name = EXCLUDED.provider_first_name,
                        provider_credential_text = EXCLUDED.provider_credential_text,
                        provider_enumeration_date = EXCLUDED.provider_enumeration_date,
                        provider_gender_code = EXCLUDED.provider_gender_code,
                        practice_state = EXCLUDED.practice_state,
                        practice_zip = EXCLUDED.practice_zip,
                        practice_phone = EXCLUDED.practice_phone,
                        taxonomy_code_1 = EXCLUDED.taxonomy_code_1,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_nppes: inserted batch %d–%d of %d",
                    start,
                    start + len(batch),
                    len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_nppes: batch insert failed")
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
