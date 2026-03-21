"""Source loader for CMS Stabilis (IV Drug Compatibility)."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsStabilisRecord(BaseModel):
    """Validated record for IV drug compatibility data."""

    drug_a: str
    drug_b: str
    compatibility: Optional[str] = None
    solvent: Optional[str] = None
    concentration: Optional[str] = None
    reference: Optional[str] = None

    @field_validator("drug_a")
    @classmethod
    def drug_a_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("drug_a must not be empty")
        return v

    @field_validator("drug_b")
    @classmethod
    def drug_b_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("drug_b must not be empty")
        return v


def load_cms_stabilis_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS Stabilis records into hcs_raw.cms_stabilis."""
    validated: List[CmsStabilisRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsStabilisRecord(**rec))
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
                        r.drug_a,
                        r.drug_b,
                        r.compatibility,
                        r.solvent,
                        r.concentration,
                        r.reference,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO hcs_raw.cms_stabilis (
                        drug_a, drug_b, compatibility, solvent,
                        concentration, reference,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (drug_a, drug_b) DO UPDATE SET
                        compatibility = EXCLUDED.compatibility,
                        solvent = EXCLUDED.solvent,
                        concentration = EXCLUDED.concentration,
                        reference = EXCLUDED.reference,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_stabilis: inserted batch %d–%d of %d",
                    start, start + len(batch), len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_stabilis: batch insert failed")
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
