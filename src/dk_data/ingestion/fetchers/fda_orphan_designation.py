"""FDA Orphan Drug Designation fetcher — OOPD database.

Source: FDA Office of Orphan Products Development (OOPD) designation database.
Public CSV download: https://www.accessdata.fda.gov/scripts/opdlisting/oopd/listResult.cfm

Stores one record per orphan designation in mol_raw.fda_orphan_designation.
Feature: 006-claims-engine-data-gaps
"""

import csv
import hashlib
import io
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_OOPD_URL = "https://www.accessdata.fda.gov/scripts/opdlisting/oopd/listResult.cfm"


class FDAOrphanDesignationFetcher(BaseFetcher):
    """Fetcher for FDA Orphan Drug Designation database (OOPD)."""

    SOURCE_NAME = "fda_orphan_designation"
    BASE_URL = "https://www.accessdata.fda.gov"

    def get_latest_url(self) -> str:
        return _OOPD_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download the OOPD CSV and return parsed records."""
        max_records: Optional[int] = kwargs.get("max_records")
        try:
            resp = self.session.get(_OOPD_URL, timeout=120)
            resp.raise_for_status()
            content = resp.content
            content_hash = hashlib.md5(content).hexdigest()

            # Parse CSV — OOPD uses a tab-delimited or comma-delimited export
            text = content.decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            records: List[Dict[str, Any]] = []
            for row in reader:
                records.append(dict(row))
                if max_records and len(records) >= max_records:
                    break

            result = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("FDAOrphanDesignation fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result
