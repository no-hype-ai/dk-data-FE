"""ACC Transcatheter Valve Certification (TVC) Fetcher.

Fetches certified TAVR site list and TVT Registry data from NCDR
Public Reporting API and CardioSmart facility downloads.

Primary data sources (in priority order):
  1. NCDR Public Reporting API — TVT-specific metrics CSV
     https://services.ncdr.com/PublicReportingApiV2/DataDownload/TVTMetrics
  2. NCDR Public Reporting API — Hospital facility list with certifications
     https://services.ncdr.com/PublicReportingApiV2/DataDownload/Hospitals
  3. Manual CSV upload fallback (for offline / gated data)

Reference pages:
  - CardioSmart: https://www.cardiosmart.org/find-your-heart-a-home/Hospitals
  - Accreditation map: https://cvquality.acc.org/accreditation/map
"""

import csv
import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


# NCDR Public Reporting API endpoints (publicly accessible CSV downloads)
NCDR_TVT_METRICS_URL = (
    "https://services.ncdr.com/PublicReportingApiV2/DataDownload/TVTMetrics"
)
NCDR_HOSPITALS_URL = (
    "https://services.ncdr.com/PublicReportingApiV2/DataDownload/Hospitals"
)


class ACCTVCFetcher(BaseFetcher):
    """Fetcher for ACC Transcatheter Valve Certification data.

    Uses the NCDR Public Reporting API which provides downloadable CSVs
    containing facility-level TAVR volumes, certification status, and
    quality metrics for hospitals participating in the STS/ACC TVT Registry.
    """

    SOURCE_NAME = "acc_tvc"
    BASE_URL = "https://services.ncdr.com/PublicReportingApiV2"

    def get_latest_url(self) -> str:
        """Return the primary data URL (TVT metrics endpoint)."""
        return NCDR_TVT_METRICS_URL

    def fetch(self, include_hospitals: bool = True) -> Dict[str, Any]:
        """Fetch ACC TVC certification and TVT Registry data.

        Tries, in order:
          1. TVTMetrics CSV  (TAVR volumes + quality ratings)
          2. Hospitals CSV   (facility info + certification columns)

        If *include_hospitals* is True (default), both datasets are fetched
        and the hospital certification columns are merged into the TVT
        records by ``FacilityLinkingID``.

        Args:
            include_hospitals: Also fetch the full Hospitals CSV to capture
                the ``TranscatheterValveCertification`` column and address
                fields.  Defaults to True.

        Returns:
            Fetch result dictionary with keys:
                status, filepath, records, hash, [hospital_filepath]
        """
        try:
            logger.info("Fetching ACC TVC data from NCDR Public Reporting API")

            # ---- 1. TVT Metrics ----
            tvt_records = self._fetch_tvt_metrics()

            # ---- 2. Hospitals (optional merge) ----
            hospital_filepath = None
            if include_hospitals:
                hospital_records, hospital_filepath = self._fetch_hospitals()

                if hospital_records and tvt_records:
                    tvt_records = self._merge_hospital_data(
                        tvt_records, hospital_records
                    )
                elif hospital_records and not tvt_records:
                    # TVT endpoint failed but hospitals worked — extract
                    # TVC-certified facilities from the hospital list.
                    tvt_records = self._extract_tvc_from_hospitals(
                        hospital_records
                    )

            if tvt_records:
                datestamp = datetime.now().strftime("%Y%m%d")
                filename = f"acc_tvc_{datestamp}.csv"
                filepath = self._write_csv(tvt_records, filename)

                result: Dict[str, Any] = {
                    "status": "success",
                    "filepath": str(filepath),
                    "records": len(tvt_records),
                    "hash": self.calculate_hash(filepath),
                }
                if hospital_filepath:
                    result["hospital_filepath"] = str(hospital_filepath)
            else:
                result = {
                    "status": "failed",
                    "error": (
                        "No data returned from NCDR API.  "
                        "Use load_manual_csv() to upload a manually "
                        "downloaded CSV from CardioSmart."
                    ),
                }

            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("Failed to fetch ACC TVC data: %s", exc)
            result = {"status": "failed", "error": str(exc)}
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_tvt_metrics(self) -> List[Dict[str, str]]:
        """Download and parse the TVTMetrics CSV.

        Returns:
            List of row dicts (all values are strings from the CSV).
        """
        try:
            logger.info("Fetching TVT Metrics from %s", NCDR_TVT_METRICS_URL)
            response = self.session.get(NCDR_TVT_METRICS_URL, timeout=120)
            response.raise_for_status()

            text = response.text
            reader = csv.DictReader(io.StringIO(text))
            records = list(reader)
            logger.info(
                "TVTMetrics: received %d facility records", len(records)
            )
            return records

        except Exception as exc:
            logger.warning("TVTMetrics fetch failed: %s", exc)
            return []

    def _fetch_hospitals(self) -> tuple[List[Dict[str, str]], Optional[Path]]:
        """Download and parse the Hospitals CSV.

        Returns:
            Tuple of (records_list, filepath_or_None).
        """
        try:
            logger.info("Fetching Hospitals from %s", NCDR_HOSPITALS_URL)
            response = self.session.get(NCDR_HOSPITALS_URL, timeout=120)
            response.raise_for_status()

            text = response.text

            # Persist the raw hospital file for audit
            datestamp = datetime.now().strftime("%Y%m%d")
            filename = f"acc_hospitals_{datestamp}.csv"
            filepath = self.data_dir / filename
            filepath.write_text(text, encoding="utf-8")

            reader = csv.DictReader(io.StringIO(text))
            records = list(reader)
            logger.info("Hospitals: received %d records", len(records))
            return records, filepath

        except Exception as exc:
            logger.warning("Hospitals fetch failed: %s", exc)
            return [], None

    @staticmethod
    def _merge_hospital_data(
        tvt_records: List[Dict[str, str]],
        hospital_records: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """Enrich TVT records with hospital address & certification columns.

        The merge key is ``FacilityLinkingID`` which is present in both CSVs.
        """
        hospital_map: Dict[str, Dict[str, str]] = {}
        address_fields = [
            "Address", "City", "State", "Zip", "Phone",
            "TranscatheterValveCertification",
        ]
        for hosp in hospital_records:
            fid = hosp.get("FacilityLinkingID", "").strip()
            if fid:
                hospital_map[fid] = {
                    k: hosp.get(k, "") for k in address_fields
                }

        merged = []
        for rec in tvt_records:
            fid = rec.get("FacilityLinkingID", "").strip()
            hosp = hospital_map.get(fid, {})
            merged_rec = {**rec, **hosp}
            merged.append(merged_rec)

        return merged

    @staticmethod
    def _extract_tvc_from_hospitals(
        hospital_records: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """Extract facilities with TranscatheterValveCertification from
        the hospitals CSV (fallback when TVTMetrics is unavailable).
        """
        tvc_facilities = []
        for hosp in hospital_records:
            cert = hosp.get("TranscatheterValveCertification", "").strip()
            # Non-empty and not "N" or "0" means certified
            if cert and cert.upper() not in ("N", "0", ""):
                tvc_facilities.append(hosp)

        logger.info(
            "Extracted %d TVC-certified facilities from hospital list",
            len(tvc_facilities),
        )
        return tvc_facilities

    def _write_csv(
        self, records: List[Dict[str, str]], filename: str
    ) -> Path:
        """Write a list of dicts to a CSV file in the data directory."""
        filepath = self.data_dir / filename
        if not records:
            filepath.write_text("", encoding="utf-8")
            return filepath

        fieldnames = list(records[0].keys())
        with open(filepath, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

        return filepath

    # ------------------------------------------------------------------
    # Manual CSV upload
    # ------------------------------------------------------------------

    def load_manual_csv(self, filepath: str) -> Dict[str, Any]:
        """Load a manually downloaded CSV file.

        This supports CSVs exported from the CardioSmart website or
        provided by ACC directly.  The file is copied into the data
        directory with a date-stamped name.

        Args:
            filepath: Path to manually downloaded CSV.

        Returns:
            Load result dictionary.
        """
        import shutil

        try:
            source_path = Path(filepath)
            if not source_path.exists():
                return {"status": "failed", "error": f"File not found: {filepath}"}

            # Copy to data directory with datestamp
            datestamp = datetime.now().strftime("%Y%m%d")
            dest_filename = f"acc_tvc_{datestamp}.csv"
            dest_path = self.data_dir / dest_filename
            shutil.copy2(source_path, dest_path)

            # Count records
            with open(dest_path, "r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                records = list(reader)

            result = {
                "status": "success",
                "filepath": str(dest_path),
                "records": len(records),
                "hash": self.calculate_hash(dest_path),
                "source": "manual_upload",
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            return {"status": "failed", "error": str(exc)}
