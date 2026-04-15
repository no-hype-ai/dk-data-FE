"""FDA Companion Diagnostic (CDx) Pairs fetcher / scraper.

Source: FDA List of Cleared or Approved Companion Diagnostic Devices
URL: https://www.fda.gov/medical-devices/in-vitro-diagnostics/
     list-cleared-or-approved-companion-diagnostic-devices-in-vitro-and-imaging-tools

The FDA publishes companion diagnostic pairing data as a downloadable table.
This fetcher scrapes/downloads the published CDx list and returns structured
records for mol_raw.fda_cdx_pairs.

Feature: 006-claims-engine-data-gaps (T034)
"""

import csv
import hashlib
import io
import logging
import re
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# FDA CDx table download URL (Excel/CSV export from FDA website)
_CDX_TABLE_URL = (
    "https://www.fda.gov/medical-devices/in-vitro-diagnostics/"
    "list-cleared-or-approved-companion-diagnostic-devices-in-vitro-and-imaging-tools"
)


class FDACDxPairsFetcher(BaseFetcher):
    """Fetcher for FDA Companion Diagnostic device-drug pairings."""

    SOURCE_NAME = "fda_cdx_pairs"
    BASE_URL = "https://www.fda.gov"

    def get_latest_url(self) -> str:
        return _CDX_TABLE_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch FDA Companion Diagnostics list.

        Attempts to scrape the HTML table from the FDA CDx page. Falls back
        to returning the raw HTML for downstream parsing if table extraction
        fails.

        Args:
            max_records: Optional cap on records returned.

        Returns:
            Fetch result dictionary.
        """
        max_records: Optional[int] = kwargs.get("max_records")

        try:
            resp = self.session.get(_CDX_TABLE_URL, timeout=120)
            resp.raise_for_status()
            html = resp.text
            content_hash = hashlib.md5(resp.content).hexdigest()

            records = self._parse_cdx_table(html)

            if max_records is not None:
                records = records[:max_records]

            result = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
                "source_url": _CDX_TABLE_URL,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("FDACDxPairs fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _parse_cdx_table(self, html: str) -> List[Dict[str, Any]]:
        """Parse companion diagnostic records from the FDA HTML page.

        Extracts rows from the main data table on the CDx listing page.
        Uses basic regex/string parsing to avoid hard dependency on bs4.
        """
        records: List[Dict[str, Any]] = []

        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            tables = soup.find_all("table")
            if not tables:
                logger.warning("No tables found on FDA CDx page")
                return records

            # Use the largest table (most rows = likely the CDx data table)
            main_table = max(tables, key=lambda t: len(t.find_all("tr")))
            rows = main_table.find_all("tr")

            # Extract headers from first row
            headers = []
            header_row = rows[0] if rows else None
            if header_row:
                for th in header_row.find_all(["th", "td"]):
                    headers.append(th.get_text(strip=True).lower())

            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue

                cell_texts = [c.get_text(strip=True) for c in cells]

                record: Dict[str, Any] = {}
                # Map by header position if we have headers
                for i, val in enumerate(cell_texts):
                    if i < len(headers):
                        record[headers[i]] = val if val else None

                # Normalize to our expected column names
                normalized = self._normalize_record(record)
                if normalized.get("device_name") or normalized.get("drug_trade_name"):
                    records.append(normalized)

        except ImportError:
            logger.warning(
                "bs4 not available; falling back to regex table parsing"
            )
            records = self._regex_parse_table(html)

        logger.info("Parsed %d CDx pair records from FDA page", len(records))
        return records

    def _normalize_record(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize scraped column names to our schema."""
        def _find(keys: List[str]) -> Optional[str]:
            for k in keys:
                for rk, rv in raw.items():
                    if k in rk.lower():
                        return rv
            return None

        return {
            "device_name": _find(["device", "diagnostic", "test"]),
            "manufacturer": _find(["manufacturer", "company", "sponsor"]),
            "intended_use": _find(["intended use", "indication"]),
            "drug_trade_name": _find(["drug trade", "drug name", "therapeutic"]),
            "drug_generic_name": _find(["generic", "active"]),
            "approval_date": _find(["date", "approval"]),
            "submission_type": _find(["submission", "type", "pma", "510"]),
            "source_url": _CDX_TABLE_URL,
        }

    def _regex_parse_table(self, html: str) -> List[Dict[str, Any]]:
        """Fallback: extract table rows via regex when bs4 is unavailable."""
        records: List[Dict[str, Any]] = []
        # Find <tr>...</tr> blocks
        tr_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
        td_pattern = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)
        tag_strip = re.compile(r"<[^>]+>")

        rows = tr_pattern.findall(html)
        for row_html in rows[1:]:  # skip header row
            cells = td_pattern.findall(row_html)
            cells = [tag_strip.sub("", c).strip() for c in cells]
            if len(cells) >= 2:
                records.append({
                    "device_name": cells[0] if len(cells) > 0 else None,
                    "manufacturer": cells[1] if len(cells) > 1 else None,
                    "intended_use": cells[2] if len(cells) > 2 else None,
                    "drug_trade_name": cells[3] if len(cells) > 3 else None,
                    "drug_generic_name": cells[4] if len(cells) > 4 else None,
                    "approval_date": cells[5] if len(cells) > 5 else None,
                    "submission_type": cells[6] if len(cells) > 6 else None,
                    "source_url": _CDX_TABLE_URL,
                })
        return records
