"""CMS Cost Reports PUF — Worksheet-Level Staffing Lines loader.

Loads worksheet A staffing line items from the HCRIS cost report files
into hcs_hcs_raw.cms_cost_reports_puf_lines.

This is the worksheet-grain companion to cms_cost_reports_puf.py.
Used by staffing_decomposition_agent to infer FTE by clinical role.
Feature: 019-cms-puf-platform-reconciliation
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from pydantic import BaseModel, ValidationError, field_validator

from ..utils.database import get_cursor, upsert_records

logger = logging.getLogger(__name__)

TABLE = "cms_cost_reports_puf_lines"
SCHEMA = "hcs_raw"

# CMS HCRIS worksheet column mapping
# The A worksheets contain staffing hours and salaries by job category
COLUMN_MAPPING = {
    # HCRIS format
    "PROVIDER_CCN": "provider_id",
    "PROVIDER_ID": "provider_id",
    "CCN": "provider_id",
    "WKSHT_CD": "line_item_code",
    "LINE_NUM": "line_item_code",
    "CLMN_NUM": "line_item_description",
    "ITM_VAL_NUM": "reported_hours_fte",
    # Human-readable format
    "Provider CCN": "provider_id",
    "Worksheet Code": "line_item_code",
    "Line Description": "line_item_description",
    "Hours / FTE": "reported_hours_fte",
    "Total Salaries": "total_salaries",
    "Facility Type": "facility_type",
    # HCRIS extract format
    "rpt_rec_num": "provider_id",
    "wkst_cd": "line_item_code",
    "line_num": "line_item_description",
    "clmn_num": "reported_hours_fte",
    "itm_val_num": "total_salaries",
}

# Staffing-relevant worksheet codes (Worksheet A series)
STAFFING_WORKSHEETS = {
    "A",
    "A-1",
    "A-2",
    "A-3",
    "A-4",
    "A-5",
    "A-6",
    "A-7",
    "A-8",
    "A-8-1",
    "A-8-2",
}


class CMSCostReportsPUFLinesRecord(BaseModel):
    provider_id: str
    line_item_code: str
    line_item_description: Optional[str] = None
    reported_hours_fte: Optional[float] = None
    total_salaries: Optional[float] = None
    facility_type: Optional[str] = None
    _source_year: int

    @field_validator("provider_id", "line_item_code", mode="before")
    @classmethod
    def strip_str(cls, v):
        return str(v).strip() if v is not None else v

    @field_validator("reported_hours_fte", "total_salaries", mode="before")
    @classmethod
    def clean_numeric(cls, v):
        if v is None or (isinstance(v, str) and v.strip() in ("", "N/A", "*")):
            return None
        try:
            return float(str(v).replace(",", "").replace("$", "").strip())
        except (ValueError, TypeError):
            return None


def load_cms_cost_reports_puf_lines(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Cost Reports PUF worksheet-level staffing lines."""
    logger.info(
        f"Loading CMS Cost Reports PUF Lines from {filepath} (year={source_year})"
    )

    source_file = Path(filepath).name
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    source_hash = hash_md5.hexdigest()

    with get_cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM {SCHEMA}.{TABLE} WHERE _source_hash = %s",
            (source_hash,),
        )
        if cur.fetchone()[0] > 0:
            logger.info(f"File {source_file} already loaded. Skipping.")
            return {
                "status": "skipped",
                "records_fetched": 0,
                "records_inserted": 0,
                "records_updated": 0,
                "errors": [],
            }

    df = pd.read_csv(filepath, dtype=str, low_memory=False)
    df = df.rename(columns=COLUMN_MAPPING)
    records_fetched = len(df)

    # Filter to staffing-relevant worksheet A lines
    if "line_item_code" in df.columns:
        df = df[
            df["line_item_code"].str.strip().str.upper().str.startswith("A")
        ]

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        if not row.get("provider_id") or not row.get("line_item_code"):
            continue
        try:
            rec = CMSCostReportsPUFLinesRecord(
                provider_id=row["provider_id"],
                line_item_code=row["line_item_code"],
                line_item_description=row.get("line_item_description"),
                reported_hours_fte=row.get("reported_hours_fte"),
                total_salaries=row.get("total_salaries"),
                facility_type=row.get("facility_type"),
                _source_year=source_year,
            )
            d = rec.model_dump()
            d["_source_hash"] = source_hash
            d["_source_file"] = source_file
            d["_loaded_at"] = loaded_at
            records.append(d)
        except (ValidationError, Exception) as e:
            if len(errors) < 10:
                errors.append(f"Row {idx}: {e}")

    inserted = upsert_records(
        SCHEMA,
        TABLE,
        records,
        conflict_columns=["provider_id", "line_item_code", "_source_year"],
        update_columns=[
            "line_item_description", "reported_hours_fte",
            "total_salaries", "facility_type", "_loaded_at",
        ],
    )

    logger.info(
        f"Cost Reports PUF Lines load complete: {inserted} records processed, "
        f"{len(errors)} errors"
    )
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors,
    }
