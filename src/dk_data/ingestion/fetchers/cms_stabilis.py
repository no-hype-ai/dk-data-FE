"""CMS Stabilis (IV Drug Compatibility) Fetcher.

Web-scrapes the Stabilis database for intravenous drug compatibility
data including solvent, concentration, and reference information.

Source: https://www.stabilis.org
"""

import logging
import re
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSStabilisFetcher(BaseFetcher):
    """Fetcher for IV drug compatibility data from Stabilis via web scraping."""

    SOURCE_NAME = "cms_stabilis"
    BASE_URL = "https://www.stabilis.org"

    def get_latest_url(self) -> str:
        """Return the Stabilis compatibility search URL."""
        return f"{self.BASE_URL}/Compatibility"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Scrape IV compatibility data from Stabilis.

        Keyword Args:
            max_records: Optional cap on returned records.
            drug_names: Optional list of drugs to query compatibility for.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records", 5000)
        drug_names: Optional[List[str]] = kwargs.get("drug_names") or self.params.get("drug_names")

        try:
            logger.info("Scraping IV compatibility data from %s", self.BASE_URL)

            records: List[Dict[str, Any]] = []

            if drug_names:
                for drug in drug_names:
                    page_records = self._fetch_drug_compatibility(drug, max_records)
                    records.extend(page_records)
                    if max_records and len(records) >= max_records:
                        records = records[:max_records]
                        break
            else:
                # Fetch the main compatibility index page
                records = self._fetch_compatibility_index(max_records)

            content_hash = self.calculate_hash(
                str(len(records)).encode()
            ) if records else None

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": content_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("Stabilis fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_drug_compatibility(
        self, drug_name: str, max_records: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Fetch compatibility data for a specific drug."""
        records: List[Dict[str, Any]] = []
        url = f"{self.BASE_URL}/Compatibility/{drug_name}"

        try:
            resp = self.session.get(url, timeout=60)
            resp.raise_for_status()
            records = self._parse_compatibility_html(resp.text, drug_name, max_records)
        except Exception as exc:
            logger.warning("Failed to fetch compatibility for %s: %s", drug_name, exc)

        return records

    def _fetch_compatibility_index(
        self, max_records: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Fetch the main compatibility index page and extract records."""
        records: List[Dict[str, Any]] = []
        url = self.get_latest_url()

        try:
            resp = self.session.get(url, timeout=60)
            resp.raise_for_status()
            records = self._parse_index_html(resp.text, max_records)

            if not records:
                # Regex may not match if Stabilis changed HTML structure.
                # Try BeautifulSoup-based fallback parsing.
                records = self._parse_index_html_bs4(resp.text, max_records)

            if not records:
                logger.warning(
                    "Stabilis scraper found 0 records from index page. "
                    "The website structure may have changed. URL: %s. "
                    "Response length: %d bytes. Manual investigation needed.",
                    url,
                    len(resp.text),
                )
        except Exception as exc:
            logger.warning("Failed to fetch compatibility index: %s", exc)

        return records

    @staticmethod
    def _parse_index_html_bs4(
        html: str, max_records: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Fallback: parse compatibility index using BeautifulSoup."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.debug("BeautifulSoup not available for Stabilis fallback parsing")
            return []

        records: List[Dict[str, Any]] = []
        soup = BeautifulSoup(html, "html.parser")

        for row in soup.select("table tr"):
            cells = row.find_all("td")
            if len(cells) >= 3:
                drug_a = cells[0].get_text(strip=True)
                drug_b = cells[1].get_text(strip=True)
                compatibility = cells[2].get_text(strip=True)

                if drug_a and drug_b:
                    records.append({
                        "drug_a": drug_a,
                        "drug_b": drug_b,
                        "compatibility": compatibility,
                        "solvent": cells[3].get_text(strip=True) if len(cells) > 3 else None,
                        "concentration": cells[4].get_text(strip=True) if len(cells) > 4 else None,
                        "reference": cells[5].get_text(strip=True) if len(cells) > 5 else None,
                    })

                if max_records and len(records) >= max_records:
                    break

        return records

    @staticmethod
    def _parse_compatibility_html(
        html: str, drug_a: str, max_records: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Parse compatibility results from a drug-specific page."""
        records: List[Dict[str, Any]] = []

        # Extract table rows containing compatibility data
        row_pattern = re.compile(
            r'<tr[^>]*>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*>([^<]+)</td>'
            r'\s*<td[^>]*>([^<]*)</td>\s*<td[^>]*>([^<]*)</td>\s*<td[^>]*>([^<]*)</td>',
            re.IGNORECASE,
        )

        for match in row_pattern.finditer(html):
            drug_b = match.group(1).strip()
            compatibility = match.group(2).strip()
            solvent = match.group(3).strip() or None
            concentration = match.group(4).strip() or None
            reference = match.group(5).strip() or None

            if drug_b:
                records.append({
                    "drug_a": drug_a,
                    "drug_b": drug_b,
                    "compatibility": compatibility,
                    "solvent": solvent,
                    "concentration": concentration,
                    "reference": reference,
                })

            if max_records and len(records) >= max_records:
                break

        return records

    @staticmethod
    def _parse_index_html(
        html: str, max_records: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Parse the compatibility index page for drug pair entries."""
        records: List[Dict[str, Any]] = []

        row_pattern = re.compile(
            r'<tr[^>]*>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*>([^<]+)</td>'
            r'\s*<td[^>]*>([^<]+)</td>',
            re.IGNORECASE,
        )

        for match in row_pattern.finditer(html):
            drug_a = match.group(1).strip()
            drug_b = match.group(2).strip()
            compatibility = match.group(3).strip()

            if drug_a and drug_b:
                records.append({
                    "drug_a": drug_a,
                    "drug_b": drug_b,
                    "compatibility": compatibility,
                    "solvent": None,
                    "concentration": None,
                    "reference": None,
                })

            if max_records and len(records) >= max_records:
                break

        return records
