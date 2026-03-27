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

            # Stream the large ZIP (500MB+) with extended timeout
            resp = self.session.get(url, timeout=(30, 600), stream=True)
            resp.raise_for_status()

            # Stream into memory in chunks to avoid read timeout
            chunks = []
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                chunks.append(chunk)
            zip_bytes = b"".join(chunks)
            logger.info("Downloaded %d MB", len(zip_bytes) // (1024 * 1024))
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
        """Extract and parse data files from the formulary ZIP.

        The CMS formulary ZIP contains nested ZIPs, each holding a
        pipe-delimited TXT file. We target the "basic drugs formulary"
        inner ZIP which contains the core formulary records.
        """
        records: List[Dict[str, Any]] = []

        try:
            outer_zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile:
            logger.error("Outer ZIP is corrupt or non-standard — cannot open")
            return records

        # Find inner ZIPs that contain formulary data (skip pharmacy networks — too large)
        target_prefixes = ("basic drugs",)
        inner_zips = [
            n for n in outer_zf.namelist()
            if n.lower().endswith(".zip")
            and any(n.lower().startswith(p) for p in target_prefixes)
        ]

        if not inner_zips:
            # Fall back to any inner ZIP that isn't pharmacy networks
            inner_zips = [
                n for n in outer_zf.namelist()
                if n.lower().endswith(".zip")
                and not n.lower().startswith("pharmacy networks")
                and not n.lower().startswith("sample")
            ]

        logger.info("Found %d inner ZIPs to process: %s", len(inner_zips), inner_zips)

        for inner_name in inner_zips:
            try:
                inner_bytes = outer_zf.read(inner_name)
                with zipfile.ZipFile(io.BytesIO(inner_bytes)) as inner_zf:
                    # Look for TXT or CSV files inside the inner ZIP
                    data_files = [
                        n for n in inner_zf.namelist()
                        if n.lower().endswith((".txt", ".csv"))
                    ]
                    for data_name in data_files:
                        logger.info("Parsing %s / %s", inner_name, data_name)
                        with inner_zf.open(data_name) as f:
                            wrapper = io.TextIOWrapper(f, encoding="utf-8")
                            reader = csv.DictReader(wrapper, delimiter="|")
                            for row in reader:
                                record = self._normalise(row)
                                if record:
                                    records.append(record)
                                if max_records and len(records) >= max_records:
                                    break
                        if max_records and len(records) >= max_records:
                            break
            except Exception as exc:
                logger.warning("Failed to process inner ZIP %s: %s", inner_name, exc)
                continue
            if max_records and len(records) >= max_records:
                break

        outer_zf.close()
        logger.info("Parsed %d formulary records from ZIP", len(records))
        return records

    @staticmethod
    def _normalise(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract key fields from a formulary record.

        The basic drugs formulary TXT uses pipe-delimited fields:
        FORMULARY_ID|FORMULARY_VERSION|CONTRACT_YEAR|RXCUI|NDC|
        TIER_LEVEL_VALUE|QUANTITY_LIMIT_YN|QUANTITY_LIMIT_AMOUNT|
        QUANTITY_LIMIT_DAYS|PRIOR_AUTHORIZATION_YN|STEP_THERAPY_YN|
        SELECTED_DRUG_YN
        """
        rxcui = item.get("RXCUI") or item.get("rxcui", "")
        formulary_id = item.get("FORMULARY_ID") or item.get("formulary_id", "")
        if not rxcui or not formulary_id:
            return None

        return {
            "formulary_id": formulary_id,
            "rxcui": rxcui,
            "ndc": item.get("NDC") or item.get("ndc"),
            "tier_level": item.get("TIER_LEVEL_VALUE") or item.get("tier_level"),
            "prior_auth": (
                item.get("PRIOR_AUTHORIZATION_YN") or item.get("PRIOR_AUTHORIZATION")
                or item.get("prior_auth")
            ),
            "step_therapy": (
                item.get("STEP_THERAPY_YN") or item.get("STEP_THERAPY")
                or item.get("step_therapy")
            ),
            "quantity_limit": (
                item.get("QUANTITY_LIMIT_YN") or item.get("QUANTITY_LIMIT")
                or item.get("quantity_limit")
            ),
            "quantity_limit_amount": (
                item.get("QUANTITY_LIMIT_AMOUNT") or item.get("quantity_limit_amount")
            ),
            "quantity_limit_days": (
                item.get("QUANTITY_LIMIT_DAYS") or item.get("quantity_limit_days")
            ),
        }
