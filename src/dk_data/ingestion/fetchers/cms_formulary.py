"""CMS Medicare Plan Formulary Fetcher.

Fetches Medicare Part D plan formulary data from CMS.
The formulary dataset is download-only (no API) — we download the latest
monthly ZIP, extract the CSV, and parse formulary records.

Source: https://data.cms.gov/medicare-part-d-plan-formulary-preference-file
"""

import csv
import hashlib
import io
import logging
import zipfile
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Latest monthly formulary ZIP — updated monthly by CMS
# Format: {year}_{YYYYMMDD}.zip
DEFAULT_FORMULARY_URL = (
    "https://data.cms.gov/sites/default/files/2026-02/"
    "d20b96a8-8acb-43cc-91e0-4f0b94c1d3f0/2026_20260219.zip"
)


class CMSFormularyFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Part D Plan Formulary data."""

    SOURCE_NAME = "cms_formulary"
    BASE_URL = "https://data.cms.gov/sites/default/files"

    def get_latest_url(self) -> str:
        """Return the CMS formulary ZIP download URL."""
        return self.params.get("download_url", DEFAULT_FORMULARY_URL)

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch formulary records from CMS ZIP download.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = (
            kwargs.get("max_records") or self.params.get("max_records")
        )

        try:
            url = self.get_latest_url()
            logger.info("Downloading formulary ZIP from %s", url)

            resp = self.session.get(url, timeout=300, stream=True)
            resp.raise_for_status()

            zip_bytes = resp.content
            content_hash = hashlib.md5(zip_bytes[:4096]).hexdigest()

            records = self._parse_zip(zip_bytes, max_records)

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": content_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("Formulary fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _parse_zip(
        self, zip_bytes: bytes, max_records: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Extract and parse CSV from the formulary ZIP."""
        records: List[Dict[str, Any]] = []

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            csv_files = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_files:
                logger.warning("No CSV files found in formulary ZIP")
                return records

            for csv_name in csv_files:
                with zf.open(csv_name) as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                    for row in reader:
                        record = self._normalise(row)
                        if record:
                            records.append(record)
                        if max_records and len(records) >= max_records:
                            break
                if max_records and len(records) >= max_records:
                    break

        logger.info("Parsed %d formulary records from ZIP", len(records))
        return records

    @staticmethod
    def _normalise(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract key fields from a formulary record."""
        rxcui = item.get("RXCUI") or item.get("rxcui", "")
        if not rxcui:
            return None

        return {
            "contract_id": item.get("CONTRACT_ID") or item.get("contract_id"),
            "plan_id": item.get("PLAN_ID") or item.get("plan_id"),
            "formulary_id": item.get("FORMULARY_ID") or item.get("formulary_id"),
            "rxcui": rxcui,
            "drug_name": item.get("DRUG_NAME") or item.get("drug_name"),
            "tier_level": item.get("TIER_LEVEL_VALUE") or item.get("tier_level"),
            "prior_auth": (
                item.get("PRIOR_AUTHORIZATION") or item.get("prior_auth")
            ),
            "step_therapy": item.get("STEP_THERAPY") or item.get("step_therapy"),
            "quantity_limit": (
                item.get("QUANTITY_LIMIT") or item.get("quantity_limit")
            ),
        }
