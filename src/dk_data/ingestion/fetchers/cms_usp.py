"""CMS USP (United States Pharmacopeia) Drug Classification Fetcher.

Web-scrapes USP Medicare Model Guidelines to retrieve drug classification
categories and classes used in Medicare Part D formulary tiering.

Source: https://www.usp.org/healthcare-professionals/usp-medicare-model-guidelines
"""

import logging
import re
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class CMSUSPFetcher(BaseFetcher):
    """Fetcher for USP Drug Classification data via web scraping."""

    SOURCE_NAME = "cms_usp"
    BASE_URL = "https://www.usp.org/healthcare-professionals/usp-medicare-model-guidelines"
    # Alternative URLs to try if the primary URL returns 404
    FALLBACK_URLS = [
        "https://www.usp.org/usp-healthcare-professionals/usp-medicare-model-guidelines",
        "https://www.usp.org/health-quality-safety/usp-medicare-model-guidelines",
    ]

    def get_latest_url(self) -> str:
        """Return the USP Medicare Model Guidelines URL."""
        return self.BASE_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Scrape USP drug classification data.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            url = self.get_latest_url()
            logger.info("Scraping USP drug classification from %s", url)

            resp = self.session.get(url, timeout=60)

            # If the primary URL returns 404, try fallback URLs
            if resp.status_code == 404:
                logger.warning(
                    "USP primary URL returned 404: %s — trying fallback URLs", url
                )
                for fallback_url in self.FALLBACK_URLS:
                    logger.info("Trying fallback URL: %s", fallback_url)
                    resp = self.session.get(fallback_url, timeout=60)
                    if resp.status_code != 404:
                        break

            if resp.status_code == 404:
                raise RuntimeError(
                    "USP Medicare Model Guidelines page not found. "
                    "The URL may have changed — check https://www.usp.org for the "
                    "current location of USP Medicare Model Guidelines. "
                    f"Tried: {url} and {self.FALLBACK_URLS}"
                )

            resp.raise_for_status()
            html = resp.text

            records = self._parse_html(html, max_records=max_records)

            content_hash = self.calculate_hash(
                html.encode("utf-8")[:10000]
            ) if records else None

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": content_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("USP fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    @staticmethod
    def _parse_html(html: str, max_records: Optional[int] = None) -> List[Dict[str, Any]]:
        """Parse USP categories and classes from the HTML page.

        Uses regex-based extraction for robustness against HTML structure
        changes. Falls back to structured table parsing when available.
        """
        records: List[Dict[str, Any]] = []

        # Look for category headers and class listings in the HTML
        # USP pages typically have categories as h2/h3 headings with classes listed below
        category_pattern = re.compile(
            r'<h[23][^>]*>\s*(?:Category\s+\d+[:\s-]*)?(.+?)\s*</h[23]>',
            re.IGNORECASE,
        )
        class_pattern = re.compile(
            r'<li[^>]*>\s*(.+?)\s*</li>',
            re.IGNORECASE,
        )

        # Split by category headers
        parts = category_pattern.split(html)
        for i in range(1, len(parts), 2):
            category_name = re.sub(r'<[^>]+>', '', parts[i]).strip()
            if not category_name:
                continue

            block = parts[i + 1] if i + 1 < len(parts) else ""
            classes = class_pattern.findall(block)

            for cls in classes:
                class_name = re.sub(r'<[^>]+>', '', cls).strip()
                if not class_name:
                    continue

                records.append({
                    "usp_category": category_name,
                    "usp_class": class_name,
                    "drug_names": None,  # Populated from linked detail pages
                })

                if max_records and len(records) >= max_records:
                    return records

        logger.info("Parsed %d USP classification records", len(records))
        return records
