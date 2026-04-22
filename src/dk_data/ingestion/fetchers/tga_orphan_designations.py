"""TGA Orphan Drug Designations fetcher.

Publishes the current orphan-drug designations list. TGA provides this as
a table on the orphan-drug-designations page; the Excel extract URL is
used when stable, otherwise we parse the HTML table.

Writes to mol_raw.tga_orphan_designations. Silver layer resolves the
designated molecule via resolve_molecule(), the sponsor via resolve_company(),
and the designated indication via resolve_condition().
"""

import csv
import hashlib
import io
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseFetcher
from ..sources.tga_orphan_designations import load_tga_orphan_designations_data

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://www.tga.gov.au/sites/default/files/orphan-drug-designations.csv"
URL_OVERRIDE_ENV = "TGA_ORPHAN_DESIGNATIONS_URL"
CHUNK_SIZE = 500


class TgaOrphanDesignationsFetcher(BaseFetcher):
    SOURCE_NAME = "tga_orphan_designations"
    BASE_URL = "https://www.tga.gov.au/resources/orphan-drug-designations"

    def __init__(self, data_dir: Optional[str] = None) -> None:
        super().__init__(data_dir)
        self.session.headers.update({
            "Accept": "text/csv, application/csv, */*",
            "User-Agent": "DK-Data-Platform/1.0 (mailto:data-platform@datakinetic.com)",
        })

    def get_latest_url(self) -> str:
        return os.getenv(URL_OVERRIDE_ENV, DEFAULT_URL)

    def fetch(self, **kwargs) -> Dict[str, Any]:
        url = self.get_latest_url()
        date_str = datetime.utcnow().strftime("%Y-%m-%d")

        try:
            resp = self.session.get(url, timeout=120)
            resp.raise_for_status()
        except Exception as exc:
            logger.exception("TGA orphan designations fetch failed: %s", exc)
            return {"status": "failed", "records": [], "record_count": 0,
                    "hash": None, "error": str(exc)}

        rows: List[Dict[str, Any]] = list(csv.DictReader(io.StringIO(resp.text)))
        total = 0
        for page_idx in range(0, len(rows), CHUNK_SIZE):
            chunk = rows[page_idx:page_idx + CHUNK_SIZE]
            page_blob = {
                "_request_id": f"tga_orphan_{date_str}_p{page_idx // CHUNK_SIZE:05d}",
                "_page_number": page_idx // CHUNK_SIZE,
                "results": chunk,
            }
            load_result = load_tga_orphan_designations_data([page_blob])
            total += load_result.get("records_inserted", 0)

        content_hash = hashlib.md5(f"{date_str}:{len(rows)}".encode()).hexdigest()
        result = {"status": "success" if total > 0 else "failed",
                  "records": [], "record_count": total, "hash": content_hash}
        self.log_fetch_result({"status": result["status"], "records": total})
        return result
