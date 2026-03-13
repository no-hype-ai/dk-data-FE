"""Source loader for CMS Post-Acute Care."""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import execute_values
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class CmsPostAcuteRecord(BaseModel):
    """Validated record for CMS post-acute care data."""

    ccn: str  # mapped to DB column provider_id
    provider_name: Optional[str] = None  # accepted from fetcher, not in DB
    provider_type: Optional[str] = None
    total_episodes: Optional[int] = None
    avg_episode_payment: Optional[float] = None  # mapped to DB column avg_spending_per_episode
    readmission_rate: Optional[float] = None  # accepted from fetcher, not in DB
    year: Optional[int] = None

    @field_validator("ccn")
    @classmethod
    def ccn_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("ccn must not be empty")
        return v


def load_cms_post_acute_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Load CMS post-acute care records into raw.cms_post_acute."""
    validated: List[CmsPostAcuteRecord] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        try:
            validated.append(CmsPostAcuteRecord(**rec))
        except Exception as exc:
            errors.append({"row": idx, "error": str(exc)})

    if not validated:
        return {
            "status": "partial" if errors else "success",
            "records_inserted": 0,
            "records_failed": len(errors),
            "errors": errors[:50],
        }

    # Filter out records with null PK fields — the DB requires (provider_id, year)
    # but the API legitimately returns records without year
    before_count = len(validated)
    validated = [r for r in validated if r.year is not None]
    skipped_null_pk = before_count - len(validated)
    if skipped_null_pk:
        logger.info(
            "cms_post_acute: skipped %d records with null PK field (year)",
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
                        r.ccn,
                        r.provider_type,
                        r.total_episodes,
                        r.avg_episode_payment,
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
                    INSERT INTO raw.cms_post_acute (
                        provider_id, provider_type, total_episodes,
                        avg_spending_per_episode, year,
                        _loaded_at, _source_file, _source_hash
                    ) VALUES %s
                    ON CONFLICT (provider_id, year) DO UPDATE SET
                        provider_type = EXCLUDED.provider_type,
                        total_episodes = EXCLUDED.total_episodes,
                        avg_spending_per_episode = EXCLUDED.avg_spending_per_episode,
                        _loaded_at = EXCLUDED._loaded_at,
                        _source_file = EXCLUDED._source_file,
                        _source_hash = EXCLUDED._source_hash
                    """,
                    values,
                )
                records_inserted += len(batch)
                logger.info(
                    "cms_post_acute: inserted batch %d–%d of %d",
                    start, start + len(batch), len(validated),
                )
            conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.exception("cms_post_acute: batch insert failed")
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
