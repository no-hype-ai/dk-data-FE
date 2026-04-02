"""CMS Medicare-Medicaid Dual Enrollment fetcher.

Downloads the CMS MDCR ENROLL AB ZIP from data.cms.gov, extracts the multi-sheet
Excel workbook, and parses three sheets to produce one normalized record per state:

  Sheet 42: Total MMEs by state → tot_benes, dual_elgbl_full_benes, dual_elgbl_prtl_benes
  Sheet 45: Original Medicare (FFS) by state → ffs_benes
  Sheet 48: Medicare Advantage by state → ma_benes

Records are returned as a list of dicts matching the hcs_raw.cms_dual_eligible schema.

Download URL (2023 data):
  https://data.cms.gov/sites/default/files/2025-09/
  1104c73c-6cb7-422c-bb24-73236d1b5767/MDCR%20ENROLL%20AB%2040-48_CPS_02ENR_2023.zip
"""

import hashlib
import io
import logging
import zipfile
from typing import Any, Dict, List, Optional, Tuple

import openpyxl

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# State name → 2-letter USPS code lookup
_STATE_CODES: Dict[str, str] = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Puerto Rico": "PR", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virgin Islands": "VI", "Virginia": "VA",
    "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "United States": "US", "All Areas": "ALL",
}

# Summary rows to skip (not individual states/territories)
_SKIP_NAMES = {"All Areas", "BLANK", "United States", ""}

_ZIP_URL = (
    "https://data.cms.gov/sites/default/files/2025-09/"
    "1104c73c-6cb7-422c-bb24-73236d1b5767/"
    "MDCR%20ENROLL%20AB%2040-48_CPS_02ENR_2023.zip"
)

# Sheet names inside the workbook
_SHEET_TOTAL = "MDCR ENROLL AB 42_CPS_02ENR"   # Total MMEs by state
_SHEET_FFS   = "MDCR ENROLL AB 45_CPS_02ENR"   # Original Medicare (FFS) by state
_SHEET_MA    = "MDCR ENROLL AB 48_CPS_02ENR"   # Medicare Advantage by state

# Data starts at row 6 (1-based): rows 1-3 titles, 4 headers, 5 blank, 6+ data
_DATA_START_ROW = 6


def _safe_int(val: Any) -> Optional[int]:
    """Return int or None for suppressed/missing values ('*', '†', None)."""
    if val is None:
        return None
    s = str(val).strip()
    if s in ("*", "†", "", "N/A"):
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _parse_state_sheet(ws) -> Dict[str, Tuple]:
    """Parse a state-level MME sheet into {state_name: (col1..col9)} mapping.

    Column order (0-based after Area of Residence):
      0: tot_mme  1: full_benefit  2: qmb_plus  3: slmb_plus  4: other_full
      5: partial  6: qmb  7: slmb  8: qdwi_qi
    """
    result: Dict[str, Tuple] = {}
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i + 1 < _DATA_START_ROW:
            continue
        if not row or row[0] is None:
            continue
        state_name = str(row[0]).strip()
        if state_name in _SKIP_NAMES or state_name.startswith("¹"):
            continue
        nums = tuple(_safe_int(row[j]) for j in range(1, 10))
        result[state_name] = nums
    return result


class CMSDualEligibleFetcher(BaseFetcher):
    """Fetcher for CMS Medicare-Medicaid Dual Eligible beneficiary data.

    Downloads the published XLSX workbook ZIP from data.cms.gov, parses three
    state-level sheets (total, FFS, MA), and returns one normalized record per
    state/territory matching the hcs_raw.cms_dual_eligible schema.
    """

    SOURCE_NAME = "cms_dual_eligible"
    BASE_URL = _ZIP_URL

    def get_latest_url(self) -> str:
        return _ZIP_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download, parse, and return state-level dual eligible records.

        Keyword Args:
            source_year: Calendar year of the data (default 2023).
            max_records: Cap number of records returned (0 = no cap).

        Returns:
            Dict with status, records (list of dicts), record_count, hash.
        """
        source_year: int = int(kwargs.get("source_year", 2023))
        max_records: int = kwargs.get("max_records", 0) or 0

        try:
            logger.info("cms_dual_eligible: downloading ZIP from data.cms.gov")
            zip_bytes = self._download_zip()
            wb = self._open_workbook(zip_bytes)

            data_total = _parse_state_sheet(wb[_SHEET_TOTAL])
            data_ffs   = _parse_state_sheet(wb[_SHEET_FFS])
            data_ma    = _parse_state_sheet(wb[_SHEET_MA])

            records: List[Dict[str, Any]] = []
            for state_name, total_nums in data_total.items():
                ffs_nums = data_ffs.get(state_name, (None,) * 9)
                ma_nums  = data_ma.get(state_name, (None,) * 9)

                # total_nums cols: (tot, full, qmb+, slmb+, other_full, partial, qmb, slmb, qdwi)
                records.append({
                    "state_cd":              _STATE_CODES.get(state_name),
                    "state_name":            state_name,
                    "dual_elgbl_lvl":        "total",
                    "dual_elgbl_desc":       "Total Medicare-Medicaid Enrollees",
                    "tot_benes":             total_nums[0],
                    "ffs_benes":             ffs_nums[0],    # total FFS MMEs (sheet 45)
                    "ma_benes":              ma_nums[0],     # total MA MMEs (sheet 48)
                    "dual_elgbl_full_benes": total_nums[1],  # full-benefit MMEs
                    "dual_elgbl_prtl_benes": total_nums[5],  # partial-benefit MMEs
                    "non_dual_benes":        None,           # not in this dataset
                    "lis_benes":             None,           # not in this dataset
                })

                if max_records and len(records) >= max_records:
                    break

            content_hash = hashlib.md5(
                f"cms_dual_eligible_{source_year}_{len(records)}".encode()
            ).hexdigest()

            logger.info(
                "cms_dual_eligible: parsed %d state records for year %d",
                len(records), source_year,
            )
            self.log_fetch_result({"status": "success", "records": len(records)})
            return {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
                "source_year": source_year,
            }

        except Exception as exc:
            logger.exception("cms_dual_eligible fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _download_zip(self) -> bytes:
        resp = self.session.get(_ZIP_URL, timeout=60)
        resp.raise_for_status()
        return resp.content

    def _open_workbook(self, zip_bytes: bytes) -> openpyxl.Workbook:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            xlsx_names = [n for n in zf.namelist() if n.endswith(".xlsx")]
            if not xlsx_names:
                raise RuntimeError("No .xlsx file found in ZIP")
            xlsx_bytes = zf.read(xlsx_names[0])
        return openpyxl.load_workbook(
            io.BytesIO(xlsx_bytes), read_only=True, data_only=True
        )
