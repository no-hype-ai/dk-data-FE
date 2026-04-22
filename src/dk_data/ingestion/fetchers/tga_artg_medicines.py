"""TGA ARTG Medicines fetcher — prescription + OTC + biologicals + complementary.

The ARTG publishes medicines as Excel extracts via the ARTG Search Visualisation
Tool and through TGA eBS bulk-extract CSVs. No REST API — we fetch the four
therapeutic-type CSVs and yield one page blob per (medicine_type, chunk).

Endpoint URLs are best-effort defaults; they may drift. Operators should set
TGA_ARTG_MEDICINES_URL_TEMPLATE env var at runtime to override. The fetcher
logs which URL it used and the row count, so drift is detectable in logs.

Therapeutic types fetched:
  - prescription
  - otc
  - biological
  - complementary

Rate limit: TGA does not publish one. We sleep REQUEST_DELAY between chunks.
"""

import csv
import hashlib
import io
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .base import BaseFetcher
from ..sources.tga_artg_medicines import load_tga_artg_medicines_data

logger = logging.getLogger(__name__)

# Default TGA ARTG Visualisation Tool CSV export endpoints. These pull the
# standard 4-way split of medicines (tga.gov.au publishes a quarterly refresh).
# If TGA changes their URL scheme, override via env var TGA_ARTG_MEDICINES_URL_TEMPLATE.
DEFAULT_URLS = {
    "prescription":  "https://www.tga.gov.au/sites/default/files/artg/prescription-medicines-artg-extract.csv",
    "otc":           "https://www.tga.gov.au/sites/default/files/artg/otc-medicines-artg-extract.csv",
    "biological":    "https://www.tga.gov.au/sites/default/files/artg/biologicals-artg-extract.csv",
    "complementary": "https://www.tga.gov.au/sites/default/files/artg/complementary-medicines-artg-extract.csv",
}

URL_OVERRIDE_ENV = "TGA_ARTG_MEDICINES_URL_TEMPLATE"  # expects format-string with {medicine_type}
REQUEST_DELAY = 1.0
CHUNK_SIZE = 500


class TgaArtgMedicinesFetcher(BaseFetcher):
    """Fetch TGA ARTG medicines (all 4 therapeutic types)."""

    SOURCE_NAME = "tga_artg_medicines"
    BASE_URL = "https://www.tga.gov.au/resources/artg"

    def __init__(self, data_dir: Optional[str] = None) -> None:
        super().__init__(data_dir)
        self.session.headers.update({
            "Accept": "text/csv, application/csv, */*",
            "User-Agent": "DK-Data-Platform/1.0 (mailto:data-platform@datakinetic.com)",
        })

    def get_latest_url(self) -> str:
        return DEFAULT_URLS["prescription"]

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch all 4 ARTG medicine types. Each type → multiple page blobs.

        Keyword Args:
            medicine_types: iterable of types to fetch (default all 4).
            full_backfill:  kept for backfill-orchestrator compatibility (no-op here).
        """
        types_to_fetch = list(kwargs.get("medicine_types") or DEFAULT_URLS.keys())

        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        grand_total = 0
        errors: List[str] = []

        for medicine_type in types_to_fetch:
            try:
                n = self._fetch_medicine_type(medicine_type, date_str)
                grand_total += n
            except Exception as exc:
                logger.warning("TGA ARTG %s fetch failed: %s", medicine_type, exc)
                errors.append(f"{medicine_type}: {exc}")

        content_hash = hashlib.md5(f"{date_str}:{grand_total}".encode()).hexdigest()
        status = "success" if grand_total > 0 else "failed"

        result = {
            "status": status,
            "records": [],                # streamed directly to DB
            "record_count": grand_total,
            "hash": content_hash,
            "errors": errors[:10],
        }
        self.log_fetch_result({"status": status, "records": grand_total})
        return result

    # ---------------------------------------------------------------

    def _fetch_medicine_type(self, medicine_type: str, date_str: str) -> int:
        template = os.getenv(URL_OVERRIDE_ENV)
        url = template.format(medicine_type=medicine_type) if template else DEFAULT_URLS[medicine_type]

        logger.info("TGA ARTG: fetching %s from %s", medicine_type, url)
        resp = self.session.get(url, timeout=300)
        resp.raise_for_status()

        total = 0
        for page_idx, chunk in enumerate(self._chunk_csv_rows(resp.text, CHUNK_SIZE)):
            page_blob = {
                "_request_id": f"tga_artg_{medicine_type}_{date_str}_p{page_idx:05d}",
                "_page_number": page_idx,
                "medicine_type": medicine_type,
                "results": chunk,
            }
            load_result = load_tga_artg_medicines_data([page_blob])
            total += load_result.get("records_inserted", 0)
            time.sleep(REQUEST_DELAY)

        logger.info("TGA ARTG %s: inserted %d page blobs (%d total rows)",
                    medicine_type, total, len(resp.text.splitlines()))
        return total

    def _chunk_csv_rows(self, csv_text: str, chunk_size: int) -> Iterator[List[Dict[str, Any]]]:
        reader = csv.DictReader(io.StringIO(csv_text))
        chunk: List[Dict[str, Any]] = []
        for row in reader:
            chunk.append(row)
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk
