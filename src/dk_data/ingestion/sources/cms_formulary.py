"""Source loader for CMS Medicare Plan Formulary."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsFormularyRecord(BaseModel):
    """Validated record for CMS formulary data."""

    contract_id: Optional[str] = None
    plan_id: Optional[str] = None
    formulary_id: Optional[str] = None
    rxcui: str
    drug_name: Optional[str] = None
    tier_level: Optional[str] = None
    prior_auth: Optional[str] = None
    step_therapy: Optional[str] = None
    quantity_limit: Optional[str] = None

    @field_validator("rxcui")
    @classmethod
    def rxcui_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("rxcui must not be empty")
        return v


def load_cms_formulary_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS formulary records into raw.cms_formulary."""
    validated: List[CmsFormularyRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsFormularyRecord(**rec))
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
                        r.contract_id,
                        r.plan_id,
                        r.formulary_id,
                        r.rxcui,
                        r.drug_name,
                        r.tier_level,
                        r.prior_auth,
                        r.step_therapy,
                        r.quantity_limit,
                        loaded_at,
                        source_file,
                        source_hash,
                    )
                    for r in batch
                ]
                execute_values(
                    cur,
                    """
                    INSERT INTO raw.cms_formulary (
                        contract_id, plan_id, formulary_id, rxcui, drug_name,
                        tier_level, prior_auth, step_therapy, quantity_limit,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (contract_id, plan_id, rxcui) DO UPDATE SET
                        formulary_id = EXCLUDED.formulary_id,
                        drug_name = EXCLUDED.drug_name,
                        tier_level = EXCLUDED.tier_level,
                        prior_auth = EXCLUDED.prior_auth,
                        step_therapy = EXCLUDED.step_therapy,
                        quantity_limit = EXCLUDED.quantity_limit,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_formulary: inserted batch %d–%d of %d",
                    start, start + len(batch), len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_formulary: batch insert failed")
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
