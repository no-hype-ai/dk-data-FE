"""WHO GHED fetcher — WHO Global Health Expenditure Database.

Fetches country-level health expenditure data from the WHO Global Health
Expenditure Database. The GHED provides standardized indicators covering
current health expenditure (CHE), government/private/out-of-pocket shares,
CHE as % of GDP, per-capita spending, and external health expenditure for
all WHO member states from 2000 to the latest available year.

API: https://apps.who.int/nha/database/Select/Indicators/en
  Bulk CSV download via the data explorer download endpoint.
  Public, no authentication required.
  Endpoint: GET /Home/DownloadAllData — returns a ZIP containing CSV.
  Fallback: direct CSV from the GHO SDMX-ML REST endpoint.

Target table: hcs_raw.who_ghed
"""

import csv
import hashlib
import io
import json
import logging
import tempfile
import zipfile
from typing import Any, Dict, List

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Primary: WHO GHED bulk CSV download (ZIP)
_GHED_DOWNLOAD_URL = (
    "https://apps.who.int/nha/database/Home/DownloadAllData"
)
# Fallback: GHO Indicator API filtered to GHED indicators
_GHO_GHED_URL = (
    "https://ghoapi.azureedge.net/api/GHED_CHE_pc_US_SHA2011"
    "?$top=10000"
)
_DEFAULT_MAX_RECORDS = 50_000
_CONTENT_LENGTH_LIMIT = 200 * 1024 * 1024  # 200 MB guard


class WHOGHEDFetcher(BaseFetcher):
    """Fetcher for WHO Global Health Expenditure Database.

    Attempts bulk CSV download first. Falls back to the GHO OData API
    for a core subset of expenditure indicators if the bulk download
    endpoint is unavailable.

    Each record is a dict with keys: country, year, indicator, value, etc.
    """

    SOURCE_NAME = "who_ghed"
    BASE_URL = "https://apps.who.int/nha/database"

    def get_latest_url(self) -> str:
        return _GHED_DOWNLOAD_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch WHO GHED health expenditure records.

        Keyword Args:
            max_records: Cap total records. Default: 50,000.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: int = int(kwargs.get("max_records", _DEFAULT_MAX_RECORDS))

        try:
            records = self._fetch_bulk_csv(max_records)

            if not records:
                logger.info("WHO GHED: bulk CSV empty, trying GHO API fallback")
                records = self._fetch_gho_fallback(max_records)

            content_hash = hashlib.md5(
                json.dumps(len(records)).encode()
            ).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("WHO GHED fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_bulk_csv(self, max_records: int) -> List[Dict[str, Any]]:
        """Download the GHED bulk CSV (possibly inside a ZIP) and parse rows."""
        logger.info("WHO GHED: attempting bulk CSV download from %s", _GHED_DOWNLOAD_URL)

        resp = self.session.get(_GHED_DOWNLOAD_URL, stream=True, timeout=300)
        resp.raise_for_status()

        # C.4 integrity guard: check Content-Length if present
        content_length = resp.headers.get("Content-Length")
        if content_length and int(content_length) > _CONTENT_LENGTH_LIMIT:
            raise ValueError(
                f"WHO GHED download too large: {content_length} bytes "
                f"(limit {_CONTENT_LENGTH_LIMIT})"
            )

        # Stream to temp file
        raw_bytes = b""
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            raw_bytes += chunk
            total += len(chunk)
            if total > _CONTENT_LENGTH_LIMIT:
                raise ValueError(
                    f"WHO GHED download exceeded {_CONTENT_LENGTH_LIMIT} bytes"
                )

        logger.info("WHO GHED: downloaded %d bytes", total)

        # Try ZIP first, then raw CSV
        records: List[Dict[str, Any]] = []
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if csv_names:
                csv_content = zf.read(csv_names[0]).decode("utf-8-sig")
                records = self._parse_csv(csv_content, max_records)
        except zipfile.BadZipFile:
            # Not a ZIP — treat as raw CSV
            csv_content = raw_bytes.decode("utf-8-sig")
            records = self._parse_csv(csv_content, max_records)

        logger.info("WHO GHED: parsed %d records from bulk CSV", len(records))
        return records

    def _parse_csv(self, csv_text: str, max_records: int) -> List[Dict[str, Any]]:
        """Parse CSV text into list of dicts."""
        reader = csv.DictReader(io.StringIO(csv_text))
        rows: List[Dict[str, Any]] = []
        for row in reader:
            if len(rows) >= max_records:
                break
            # Tag with source for routing
            row["_source"] = "who_ghed"
            rows.append(dict(row))
        return rows

    def _fetch_gho_fallback(self, max_records: int) -> List[Dict[str, Any]]:
        """Fallback: fetch core GHED indicators from the GHO OData API."""
        # Key GHED indicators available via GHO API
        indicators = [
            "GHED_CHE_pc_US_SHA2011",    # CHE per capita (USD)
            "GHED_CHE_GDPSHA2011",       # CHE as % of GDP
            "GHED_GGHE-DSHA2011",        # Domestic general govt health exp
            "GHED_OOPS_SHA2011",         # Out-of-pocket spending
            "GHED_EXTSHA2011",           # External health expenditure
        ]

        all_records: List[Dict[str, Any]] = []
        for indicator_code in indicators:
            if len(all_records) >= max_records:
                break
            url = f"https://ghoapi.azureedge.net/api/{indicator_code}?$top=10000"
            try:
                resp = self.session.get(url, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                values = data.get("value", [])
                for v in values:
                    v["IndicatorCode"] = indicator_code
                    v["_source"] = "who_ghed"
                all_records.extend(values)
                logger.info(
                    "WHO GHED GHO fallback: %s -> %d records",
                    indicator_code, len(values),
                )
            except Exception as exc:
                logger.warning(
                    "WHO GHED GHO fallback failed for %s: %s",
                    indicator_code, exc,
                )

        return all_records[:max_records]
