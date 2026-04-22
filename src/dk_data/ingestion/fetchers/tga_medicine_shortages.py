"""TGA Medicine Shortages fetcher — Medicine Shortages Information portal (MSI).

MSI publishes current and resolved medicine shortages across Australia.
Query endpoint returns JSON. Writes to mol_raw.tga_medicine_shortages.
"""

import hashlib
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseFetcher
from ..sources.tga_medicine_shortages import load_tga_medicine_shortages_data

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://apps.tga.gov.au/prod/MSI/search"
URL_OVERRIDE_ENV = "TGA_MSI_URL"
PAGE_SIZE = 100
REQUEST_DELAY = 0.5


class TgaMedicineShortagesFetcher(BaseFetcher):
    SOURCE_NAME = "tga_medicine_shortages"
    BASE_URL = DEFAULT_URL

    def __init__(self, data_dir: Optional[str] = None) -> None:
        super().__init__(data_dir)
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "DK-Data-Platform/1.0 (mailto:data-platform@datakinetic.com)",
        })

    def get_latest_url(self) -> str:
        return os.getenv(URL_OVERRIDE_ENV, DEFAULT_URL)

    def fetch(self, **kwargs) -> Dict[str, Any]:
        max_records = int(kwargs.get("max_records", 10_000))
        date_str = datetime.utcnow().strftime("%Y-%m-%d")

        url = self.get_latest_url()
        total = 0
        page_num = 0

        while total < max_records:
            params = {"pageSize": PAGE_SIZE, "page": page_num}
            try:
                data = self.fetch_json(url, params=params)
            except Exception as exc:
                logger.warning("TGA MSI page=%d fetch failed: %s", page_num, exc)
                break

            results = data.get("results") or data.get("items") or []
            if not results:
                break

            page_blob = {
                "_request_id": f"tga_msi_{date_str}_p{page_num:05d}",
                "_page_number": page_num,
                "results": results,
            }
            load_result = load_tga_medicine_shortages_data([page_blob])
            total += load_result.get("records_inserted", 0)
            page_num += 1

            if len(results) < PAGE_SIZE:
                break
            time.sleep(REQUEST_DELAY)

        content_hash = hashlib.md5(f"{date_str}:{total}".encode()).hexdigest()
        result = {"status": "success" if total > 0 else "failed",
                  "records": [], "record_count": total, "hash": content_hash}
        self.log_fetch_result({"status": result["status"], "records": total})
        return result
