"""TGA ARTG Medical Devices fetcher — dev_ domain.

Fetches the ARTG medical-device extract (Excel/CSV) from TGA. Writes to
dev_raw.tga_artg_devices. Silver layer resolves applicant strings via
mol_silver.resolve_company() and canonical device identity via
dev_silver.resolve_device().
"""

import csv
import hashlib
import io
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from .base import BaseFetcher
from ..sources.tga_artg_devices import load_tga_artg_devices_data

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://www.tga.gov.au/sites/default/files/artg/medical-devices-artg-extract.csv"
URL_OVERRIDE_ENV = "TGA_ARTG_DEVICES_URL"
REQUEST_DELAY = 1.0
CHUNK_SIZE = 500


class TgaArtgDevicesFetcher(BaseFetcher):
    SOURCE_NAME = "tga_artg_devices"
    BASE_URL = "https://www.tga.gov.au/resources/artg"

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
            logger.info("TGA ARTG devices: fetching %s", url)
            resp = self.session.get(url, timeout=600)
            resp.raise_for_status()
        except Exception as exc:
            logger.exception("TGA ARTG devices fetch failed: %s", exc)
            return {"status": "failed", "records": [], "record_count": 0,
                    "hash": None, "error": str(exc)}

        total = 0
        for page_idx, chunk in enumerate(self._chunk_csv_rows(resp.text, CHUNK_SIZE)):
            page_blob = {
                "_request_id": f"tga_artg_devices_{date_str}_p{page_idx:05d}",
                "_page_number": page_idx,
                "results": chunk,
            }
            load_result = load_tga_artg_devices_data([page_blob])
            total += load_result.get("records_inserted", 0)
            time.sleep(REQUEST_DELAY)

        content_hash = hashlib.md5(f"{date_str}:{total}".encode()).hexdigest()
        result = {"status": "success", "records": [], "record_count": total, "hash": content_hash}
        self.log_fetch_result({"status": "success", "records": total})
        return result

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
