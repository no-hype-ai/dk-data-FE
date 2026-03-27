"""NIH Reporter loader — inserts to mol_raw.nih_reporter_raw."""
import logging
from datetime import datetime
from typing import List, Optional

from ..utils.database import get_cursor, upsert_records

logger = logging.getLogger(__name__)


def _extract_pi_names(project: dict) -> Optional[str]:
    """Extract PI names list as a string for storage."""
    pi_list = project.get("principal_investigators")
    if not pi_list:
        return None
    return str(pi_list)


def _extract_award_amount(project: dict) -> Optional[float]:
    """Extract award amount, handling None and non-numeric values."""
    raw = project.get("award_amount")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def load_nih_reporter_data(records: list, source_hash: Optional[str] = None) -> dict:
    """
    Load NIH Reporter project records into mol_raw.nih_reporter_raw.

    Args:
        records: List of raw API response dicts from NIHReporterFetcher.
        source_hash: Optional content hash string (unused for this source).

    Returns:
        Standard result dict with status, records_fetched, records_inserted, records_updated, errors.
    """
    if not records:
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    rows = []
    errors: List[str] = []

    for r in records:
        project_number = r.get("project_num") or r.get("project_number")
        if not project_number:
            continue
        try:
            org = r.get("organization") or {}
            org_name = org.get("org_name") if isinstance(org, dict) else None

            fiscal_year_raw = r.get("fiscal_year")
            try:
                fiscal_year = int(fiscal_year_raw) if fiscal_year_raw is not None else None
            except (TypeError, ValueError):
                fiscal_year = None

            rows.append({
                "project_number": str(project_number),
                "project_title": r.get("project_title"),
                "fiscal_year": fiscal_year,
                "award_amount": _extract_award_amount(r),
                "pi_names": _extract_pi_names(r),
                "organization_name": org_name,
                "abstract_text": r.get("abstract_text"),
                "project_start_date": r.get("project_start_date"),
                "project_end_date": r.get("project_end_date"),
                "response_body": str(r),
                "_loaded_at": datetime.utcnow(),
            })
        except Exception as e:
            errors.append(f"project_number={project_number}: {e}")
            logger.warning(f"NIH Reporter row error for project_number={project_number}: {e}")

    if not rows:
        return {
            "status": "success",
            "records_fetched": len(records),
            "records_inserted": 0,
            "records_updated": 0,
            "errors": errors[:10],
        }

    inserted = upsert_records(
        "mol_raw",
        "nih_reporter_raw",
        rows,
        conflict_columns=["project_number"],
        update_columns=[
            "project_title",
            "fiscal_year",
            "award_amount",
            "pi_names",
            "organization_name",
            "abstract_text",
            "project_start_date",
            "project_end_date",
            "_loaded_at",
        ],
    )

    logger.info(
        f"NIH Reporter load complete: {inserted} upserted from {len(records)} fetched records"
    )

    return {
        "status": "success",
        "records_fetched": len(records),
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
