"""CMS NUCC (National Uniform Claim Committee) Provider Taxonomy Fetcher.

Downloads the NUCC Health Care Provider Taxonomy code set CSV,
mapping taxonomy codes to provider types, classifications, and specializations.

Source: https://nucc.org/index.php/code-sets-mainmenu-41/provider-taxonomy-mainmenu-40
"""

import csv
import hashlib
import io
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

NUCC_CSV_URL = "https://nucc.org/images/stories/CSV/nucc_taxonomy_240.csv"


class CMSNUCCFetcher(BaseFetcher):
    """Fetcher for NUCC Health Care Provider Taxonomy CSV."""

    SOURCE_NAME = "cms_nucc"
    BASE_URL = "https://nucc.org/index.php/code-sets-mainmenu-41/provider-taxonomy-mainmenu-40"

    def get_latest_url(self) -> str:
        """Return the NUCC taxonomy CSV download URL."""
        return self.params.get("csv_url", NUCC_CSV_URL)

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download and parse the NUCC taxonomy CSV.

        Keyword Args:
            max_records: Optional cap on returned records.

        Returns:
            Fetch result dict with status, records list, and hash.
        """
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            url = self.get_latest_url()
            logger.info("Downloading NUCC taxonomy CSV from %s", url)

            resp = self.session.get(url, timeout=60)
            resp.raise_for_status()
            content = resp.text

            content_hash = hashlib.md5(content.encode("utf-8")[:50000]).hexdigest()

            records = self._parse_csv(content, max_records=max_records)

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "hash": content_hash,
            }
            self.log_fetch_result(result)
            return result

        except Exception as exc:
            logger.exception("NUCC fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    @staticmethod
    def _parse_csv(content: str, max_records: Optional[int] = None) -> List[Dict[str, Any]]:
        """Parse the NUCC taxonomy CSV content."""
        records: List[Dict[str, Any]] = []
        reader = csv.DictReader(io.StringIO(content))

        for row in reader:
            code = (row.get("Code") or row.get("code", "")).strip()
            if not code:
                continue

            records.append({
                "taxonomy_code": code,
                "taxonomy_type": (row.get("Grouping") or row.get("Type", "")).strip() or None,
                "classification": (row.get("Classification") or "").strip() or None,
                "specialization": (row.get("Specialization") or "").strip() or None,
            })

            if max_records and len(records) >= max_records:
                break

        logger.info("Parsed %d NUCC taxonomy records", len(records))
        return records
