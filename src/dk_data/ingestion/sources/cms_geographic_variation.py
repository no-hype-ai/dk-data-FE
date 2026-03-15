"""Source loader for CMS Geographic Variation."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsGeographicVariationRecord(BaseModel):
    """Validated record for CMS geographic variation data."""

    state: str
    county: Optional[str] = None
    total_beneficiaries: Optional[int] = None  # mapped to DB column bene_count
    total_actual_costs: Optional[float] = None
    per_capita_costs: Optional[float] = None
    ip_covered_stays_per_1000: Optional[float] = None  # accepted from fetcher, not in DB
    er_visits_per_1000: Optional[float] = None  # accepted from fetcher, not in DB
    year: Optional[int] = None

    @field_validator("state")
    @classmethod
    def state_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("state must not be empty")
        return v

    @field_validator(
        "total_beneficiaries", "total_actual_costs", "per_capita_costs",
        "ip_covered_stays_per_1000", "er_visits_per_1000", "year",
        mode="before",
    )
    @classmethod
    def coerce_numeric(cls, v):
        """CMS uses '*' for suppressed values — treat as None."""
        if v is None or v == "" or v == "*":
            return None
        return v


def load_cms_geographic_variation_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS geographic variation records into raw.cms_geographic_variation."""
    validated: List[CmsGeographicVariationRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsGeographicVariationRecord(**rec))
        except Exception as exc:
            errors.append({"row": idx, "error": str(exc)})

    if not validated:
        return {
            "status": "partial" if errors else "success",
            "records_inserted": 0,
            "records_failed": len(errors),
            "errors": errors[:50],
        }

    # Coerce year to int and filter records missing year (required PK field)
    for r in validated:
        if r.year is not None:
            try:
                r.year = int(r.year)
            except (ValueError, TypeError):
                r.year = None
    before_count = len(validated)
    validated = [r for r in validated if r.year is not None]
    skipped = before_count - len(validated)
    if skipped:
        logger.info("cms_geographic_variation: skipped %d records with null year", skipped)

    # Deduplicate by PK (state, year) — API returns multiple cohort rows per state/year;
    # keep the first (largest bene_count) per key
    seen: dict = {}
    for r in validated:
        key = (r.state, r.year)
        if key not in seen:
            seen[key] = r
    deduped = before_count - len(validated)
    validated = list(seen.values())

    if not validated:
        return {
            "status": "success",
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
                        r.state,
                        r.county,
                        r.total_beneficiaries,
                        r.total_actual_costs,
                        r.per_capita_costs,
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
                    INSERT INTO raw.cms_geographic_variation (
                        state, county, bene_count, total_actual_costs,
                        per_capita_costs, year,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (state, year) DO UPDATE SET
                        county = EXCLUDED.county,
                        bene_count = EXCLUDED.bene_count,
                        total_actual_costs = EXCLUDED.total_actual_costs,
                        per_capita_costs = EXCLUDED.per_capita_costs,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_geographic_variation: inserted batch %d–%d of %d",
                    start, start + len(batch), len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_geographic_variation: batch insert failed")
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
