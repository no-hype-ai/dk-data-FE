"""PBS Australia fetcher — Pharmaceutical Benefits Scheme schedule data.

Fetches the Australian PBS Schedule from the Department of Health publication
endpoint. The PBS lists all medicines subsidised by the Australian Government
for community use, with pricing, restrictions, and therapeutic classification.

API: https://www.pbs.gov.au/publication/schedule/
  Public, no authentication required.
  The PBS publishes a machine-readable CSV/XML schedule file monthly.
  Endpoint: GET /downloads/medicine-listing/current
  Alternative: API v3 at https://data.pbs.gov.au/

  Both are free and open. The data.pbs.gov.au API provides structured JSON.

Target table: mol_raw.pbs_australia
"""

import csv
import hashlib
import io
import json
import logging
import time
import zipfile
from typing import Any, Dict, List

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# PBS data API (structured JSON) — preferred endpoint
_PBS_API_BASE = "https://data.pbs.gov.au/api/v3"
# PBS schedule CSV download
_PBS_CSV_URL = (
    "https://www.pbs.gov.au/publication/schedule/2026/04/"
    "pbs-standard-schedule-20260401.csv"
)
# Fallback: generic latest download URL
_PBS_DOWNLOAD_URL = "https://www.pbs.gov.au/downloads/medicine-listing"
_DEFAULT_MAX_RECORDS = 50_000
_CONTENT_LENGTH_LIMIT = 100 * 1024 * 1024  # 100 MB guard
_PAGE_SIZE = 500
_REQUEST_DELAY = 0.5


class PBSAustraliaFetcher(BaseFetcher):
    """Fetcher for Australian PBS pharmaceutical schedule data.

    Attempts the structured data.pbs.gov.au API first (paginated JSON).
    Falls back to bulk CSV download from pbs.gov.au if the API is
    unavailable.

    Each record is a dict with item_code, drug_name, form, manner_of_admin,
    brand_name, manufacturer, price, and schedule_code.
    """

    SOURCE_NAME = "pbs_australia"
    BASE_URL = _PBS_API_BASE

    def get_latest_url(self) -> str:
        return f"{_PBS_API_BASE}/items?limit={_PAGE_SIZE}&offset=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch PBS schedule records.

        Keyword Args:
            max_records: Cap total records. Default: 50,000.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: int = int(kwargs.get("max_records", _DEFAULT_MAX_RECORDS))

        try:
            # Try the structured API first
            records = self._fetch_api(max_records)

            if not records:
                logger.info("PBS Australia: API returned no data, trying CSV download")
                records = self._fetch_csv(max_records)

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
            logger.exception("PBS Australia fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_api(self, max_records: int) -> List[Dict[str, Any]]:
        """Fetch PBS items from the data.pbs.gov.au API (paginated JSON)."""
        all_records: List[Dict[str, Any]] = []
        offset = 0

        while len(all_records) < max_records:
            url = f"{_PBS_API_BASE}/items?limit={_PAGE_SIZE}&offset={offset}"
            try:
                resp = self.session.get(url, timeout=60)
                if resp.status_code == 404:
                    # API may not be available — fall through to CSV
                    logger.info("PBS API returned 404 — will try CSV fallback")
                    return []
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning(
                    "PBS API fetch failed at offset=%d: %s", offset, exc
                )
                break

            # Handle both list and dict responses
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("items", data.get("data", data.get("results", [])))
            else:
                break

            if not items:
                break

            for item in items:
                if len(all_records) >= max_records:
                    break
                item["_source"] = "pbs_australia"
                all_records.append(item)

            if len(items) < _PAGE_SIZE:
                break

            offset += _PAGE_SIZE
            time.sleep(_REQUEST_DELAY)

        logger.info("PBS Australia API: fetched %d records", len(all_records))
        return all_records

    def _fetch_csv(self, max_records: int) -> List[Dict[str, Any]]:
        """Download PBS schedule CSV as fallback."""
        logger.info("PBS Australia: attempting CSV download")

        # Try the direct CSV URL first, then the generic download
        for url in [_PBS_CSV_URL, _PBS_DOWNLOAD_URL]:
            try:
                resp = self.session.get(url, stream=True, timeout=300)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()

                # C.4 integrity guard
                content_length = resp.headers.get("Content-Length")
                if content_length and int(content_length) > _CONTENT_LENGTH_LIMIT:
                    raise ValueError(
                        f"PBS CSV too large: {content_length} bytes"
                    )

                raw_bytes = b""
                total = 0
                for chunk in resp.iter_content(chunk_size=65536):
                    raw_bytes += chunk
                    total += len(chunk)
                    if total > _CONTENT_LENGTH_LIMIT:
                        raise ValueError(
                            f"PBS CSV exceeded {_CONTENT_LENGTH_LIMIT} bytes"
                        )

                logger.info("PBS Australia: downloaded %d bytes", total)

                # Try ZIP, then raw CSV
                records: List[Dict[str, Any]] = []
                try:
                    zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
                    csv_names = [
                        n for n in zf.namelist() if n.lower().endswith(".csv")
                    ]
                    if csv_names:
                        csv_text = zf.read(csv_names[0]).decode("utf-8-sig")
                        records = self._parse_csv(csv_text, max_records)
                except zipfile.BadZipFile:
                    csv_text = raw_bytes.decode("utf-8-sig")
                    records = self._parse_csv(csv_text, max_records)

                if records:
                    logger.info(
                        "PBS Australia CSV: parsed %d records from %s",
                        len(records), url,
                    )
                    return records

            except Exception as exc:
                logger.warning("PBS Australia CSV download failed for %s: %s", url, exc)
                continue

        return []

    def _parse_csv(self, csv_text: str, max_records: int) -> List[Dict[str, Any]]:
        """Parse PBS CSV text into list of dicts."""
        reader = csv.DictReader(io.StringIO(csv_text))
        rows: List[Dict[str, Any]] = []
        for row in reader:
            if len(rows) >= max_records:
                break
            row["_source"] = "pbs_australia"
            rows.append(dict(row))
        return rows
