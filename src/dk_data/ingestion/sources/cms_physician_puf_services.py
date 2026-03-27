"""CMS Physician PUF by Provider and Service loader.

Loads NPI × HCPCS-level detail from the Medicare Physician and Other
Practitioners – by Provider and Service annual file into
hcs_raw.cms_physician_puf_services.

This is the HCPCS-grain companion to cms_physician_puf.py (which is NPI-grain).
Used by equipment_inventory_agent to infer medical equipment from HCPCS patterns.
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

TABLE = "cms_physician_puf_services"
SCHEMA = "hcs_raw"

# CMS column mapping — handles both old and new file formats
COLUMN_MAPPING = {
    # Current format (post-2020) — matches CMS canonical column names
    "Rndrng_NPI": "npi",
    "Rndrng_Prvdr_Last_Org_Name": "provider_last_org_name",
    "Rndrng_Prvdr_First_Name": "provider_first_name",
    "Rndrng_Prvdr_Type": "provider_type",
    "Rndrng_Prvdr_State_Abrvtn": "provider_state",
    "Rndrng_Prvdr_State_FIPS": "provider_state_fips",
    "Rndrng_Prvdr_RUCA": "provider_ruca",
    "HCPCS_Cd": "hcpcs_code",
    "HCPCS_Desc": "hcpcs_description",
    "HCPCS_Drug_Ind": "hcpcs_drug_ind",
    "Place_Of_Srvc": "place_of_service",
    "Tot_Benes": "bene_unique_cnt",
    "Tot_Srvcs": "line_srvc_cnt",
    "Tot_Bene_Day_Srvcs": "bene_day_srvc_cnt",
    "Avg_Sbmtd_Chrg": "average_submitted_chrg_amt",
    "Avg_Mdcr_Alowd_Amt": "average_medicare_allowed_amt",
    "Avg_Mdcr_Pymt_Amt": "average_medicare_payment_amt",
    "Avg_Mdcr_Stdzd_Amt": "average_medicare_stnd_amt",
    # Legacy format (pre-2020)
    "National Provider Identifier": "npi",
    "HCPCS Code": "hcpcs_code",
    "HCPCS Description": "hcpcs_description",
    "Number of Services": "line_srvc_cnt",
    "Number of Medicare Beneficiaries": "bene_unique_cnt",
    "Number of Distinct Medicare Beneficiary/Per Day Services": "bene_day_srvc_cnt",
    "Average Submitted Charge Amount": "average_submitted_chrg_amt",
    "Average Medicare Allowed Amount": "average_medicare_allowed_amt",
    "Average Medicare Payment Amount": "average_medicare_payment_amt",
    "Place of Service": "place_of_service",
}


class CMSPhysicianPUFServicesRecord(BaseModel):
    """CMS Physician PUF by Provider and Service (NPI × HCPCS grain).

    CMS columns: Rndrng_NPI, HCPCS_Cd, HCPCS_Desc, HCPCS_Drug_Ind,
    Place_Of_Srvc, Tot_Benes, Tot_Srvcs, Tot_Bene_Day_Srvcs,
    Avg_Sbmtd_Chrg, Avg_Mdcr_Alowd_Amt, Avg_Mdcr_Pymt_Amt, Avg_Mdcr_Stdzd_Amt.
    """

    npi: str
    hcpcs_code: str
    hcpcs_description: Optional[str] = None
    hcpcs_drug_ind: Optional[str] = None
    place_of_service: Optional[str] = None
    line_srvc_cnt: Optional[float] = None
    bene_unique_cnt: Optional[int] = None
    bene_day_srvc_cnt: Optional[int] = None
    average_submitted_chrg_amt: Optional[float] = None
    average_medicare_allowed_amt: Optional[float] = None
    average_medicare_payment_amt: Optional[float] = None
    average_medicare_stnd_amt: Optional[float] = None
    _source_year: int

    @field_validator("npi", "hcpcs_code", mode="before")
    @classmethod
    def strip_whitespace(cls, v):
        return str(v).strip() if v is not None else v

    @field_validator("line_srvc_cnt", "average_submitted_chrg_amt",
                     "average_medicare_allowed_amt", "average_medicare_payment_amt",
                     "average_medicare_stnd_amt",
                     mode="before")
    @classmethod
    def clean_numeric(cls, v):
        if v is None or (isinstance(v, str) and v.strip() in ("", "N/A", "*")):
            return None
        return float(str(v).replace(",", "").replace("$", "").strip())

    @field_validator("bene_unique_cnt", "bene_day_srvc_cnt", mode="before")
    @classmethod
    def clean_int(cls, v):
        if v is None or (isinstance(v, str) and v.strip() in ("", "N/A", "*")):
            return None
        try:
            return int(float(str(v).replace(",", "").strip()))
        except (ValueError, TypeError):
            return None


def load_cms_physician_puf_services(filepath: str, source_year: int = 2023) -> dict:
    """Load CMS Physician PUF by Provider and Service (HCPCS grain)."""
    logger.info(f"Loading CMS Physician PUF Services from {filepath} (year={source_year})")

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

    records = []
    errors = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for idx, row in df.iterrows():
        if not row.get("npi") or not row.get("hcpcs_code"):
            continue
        try:
            rec = CMSPhysicianPUFServicesRecord(
                npi=row["npi"],
                hcpcs_code=row["hcpcs_code"],
                hcpcs_description=row.get("hcpcs_description"),
                hcpcs_drug_ind=row.get("hcpcs_drug_ind"),
                place_of_service=row.get("place_of_service"),
                line_srvc_cnt=row.get("line_srvc_cnt"),
                bene_unique_cnt=row.get("bene_unique_cnt"),
                bene_day_srvc_cnt=row.get("bene_day_srvc_cnt"),
                average_submitted_chrg_amt=row.get("average_submitted_chrg_amt"),
                average_medicare_allowed_amt=row.get("average_medicare_allowed_amt"),
                average_medicare_payment_amt=row.get("average_medicare_payment_amt"),
                average_medicare_stnd_amt=row.get("average_medicare_stnd_amt"),
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
        conflict_columns=["npi", "hcpcs_code", "place_of_service", "_source_year"],
        update_columns=[
            "hcpcs_description", "hcpcs_drug_ind",
            "line_srvc_cnt", "bene_unique_cnt", "bene_day_srvc_cnt",
            "average_submitted_chrg_amt", "average_medicare_allowed_amt",
            "average_medicare_payment_amt", "average_medicare_stnd_amt",
            "_loaded_at",
        ],
    )

    logger.info(
        f"Physician PUF Services load complete: {inserted} records processed, "
        f"{len(errors)} errors"
    )
    return {
        "status": "success",
        "records_fetched": records_fetched,
        "records_inserted": inserted,
        "records_updated": 0,
        "errors": errors,
    }
