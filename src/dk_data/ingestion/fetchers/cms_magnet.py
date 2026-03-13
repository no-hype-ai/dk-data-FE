"""ANCC Magnet Recognition Fetcher.

Scrapes the ANCC (American Nurses Credentialing Center) website for
hospitals with Magnet designation status. Uses BeautifulSoup for
HTML parsing.

Feature: 016-cms-puf-datasource-integration (Phase 3)

Source: https://www.nursingworld.org/organizational-programs/magnet
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Key output fields
KEY_FIELDS = [
    "facility_name",
    "city",
    "state",
    "designation_date",
    "redesignation_date",
]

# ANCC directory listing URL
MAGNET_DIRECTORY_URL = "https://www.nursingworld.org/organizational-programs/magnet/find-a-magnet-organization/"


class CMSMagnetFetcher(BaseFetcher):
    """Fetcher for ANCC Magnet Recognition data (web scrape)."""

    SOURCE_NAME = "cms_magnet"
    BASE_URL = "https://www.nursingworld.org/organizational-programs/magnet"

    def get_latest_url(self) -> str:
        """Return the URL for the Magnet organization directory."""
        return MAGNET_DIRECTORY_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Scrape ANCC Magnet designation data using BeautifulSoup.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            records = self._scrape_directory(max_records=max_records)
            file_hash = self._save_and_hash(records)

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": file_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("Magnet fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scrape_directory(
        self,
        max_records: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Scrape the Magnet organization directory.

        Args:
            max_records: Optional record cap.

        Returns:
            List of Magnet facility record dicts.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("BeautifulSoup (bs4) is required for Magnet scraping")
            raise ImportError(
                "beautifulsoup4 is required for Magnet scraping. "
                "Install with: pip install beautifulsoup4"
            )

        records: List[Dict[str, Any]] = []

        logger.info("Scraping Magnet directory from %s", MAGNET_DIRECTORY_URL)
        response = self.session.get(MAGNET_DIRECTORY_URL, timeout=120)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Parse organization entries from the directory listing
        # The exact selectors depend on the ANCC website structure
        # Try multiple CSS selector strategies — the ANCC website
        # structure changes frequently.
        selector_strategies = [
            ".magnet-organization, .organization-listing, .directory-entry, .org-item",
            "table tbody tr",
            ".card, .list-group-item, .result-item",
            "article, .content-item",
            "tr",
        ]

        for selectors in selector_strategies:
            org_entries = soup.select(selectors)
            if org_entries:
                for entry in org_entries:
                    record = self._parse_entry(entry)
                    if record and record.get("facility_name"):
                        records.append(record)
                        if max_records and len(records) >= max_records:
                            break
                if records:
                    break

        if not records:
            logger.warning(
                "Magnet scraper found 0 organizations. The ANCC website "
                "structure may have changed. URL: %s. "
                "Response length: %d bytes. Manual investigation needed.",
                MAGNET_DIRECTORY_URL,
                len(response.text),
            )

        logger.info("Scraped %d Magnet organizations", len(records))
        return records

    @staticmethod
    def _parse_entry(entry) -> Optional[Dict[str, Any]]:
        """Parse a single organization entry from the HTML.

        Args:
            entry: BeautifulSoup element representing one organization.

        Returns:
            Record dict or None if parsing fails.
        """
        try:
            # Try table row format
            cells = entry.find_all("td")
            if len(cells) >= 3:
                return {
                    "facility_name": cells[0].get_text(strip=True) or None,
                    "city": cells[1].get_text(strip=True) if len(cells) > 1 else None,
                    "state": cells[2].get_text(strip=True) if len(cells) > 2 else None,
                    "designation_date": cells[3].get_text(strip=True) if len(cells) > 3 else None,
                    "redesignation_date": cells[4].get_text(strip=True) if len(cells) > 4 else None,
                }

            # Try div/span structured format
            name_el = entry.select_one(
                ".org-name, .facility-name, h3, h4, strong"
            )
            if not name_el:
                return None

            facility_name = name_el.get_text(strip=True)
            if not facility_name:
                return None

            # Extract location from sibling or child elements
            location_el = entry.select_one(
                ".location, .city-state, .address, p"
            )
            city = None
            state = None
            if location_el:
                text = location_el.get_text(strip=True)
                parts = text.split(",")
                if len(parts) >= 2:
                    city = parts[0].strip()
                    state = parts[1].strip()

            # Extract dates
            date_el = entry.select_one(".designation-date, .date")
            designation_date = date_el.get_text(strip=True) if date_el else None

            return {
                "facility_name": facility_name,
                "city": city,
                "state": state,
                "designation_date": designation_date,
                "redesignation_date": None,
            }

        except Exception:
            return None

    def _save_and_hash(self, records: List[Dict]) -> Optional[str]:
        """Persist records to a JSON file and return its MD5 hash."""
        import json

        if not records:
            return None

        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"cms_magnet_{timestamp}.json"
        filepath = self.data_dir / filename

        with open(filepath, "w") as fh:
            json.dump(records, fh)

        return self.calculate_hash(filepath)
