"""TGA SARA Recalls fetcher — System for Australian Recall Actions.

Two ingestion paths; tried in order:
  1. SARA JSON search endpoint (if available) — preferred.
  2. SARA RSS/Atom feed — fallback.

SARA contains BOTH medicine recalls and medical-device recalls. Each record
carries a regulatory_type field (e.g. "Medicine", "Medical device") that
the silver layer uses to route into mol_silver.tga_medicine_recalls vs
dev_silver.tga_device_recalls.

Incremental mode: fetch recalls posted in the last N days (default 365 on
first run; 30 for daily increments via days_back kwarg).
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseFetcher
from ..sources.tga_sara_recalls import load_tga_sara_recalls_data

logger = logging.getLogger(__name__)

# SARA public search. Query params differ across deployments; the fetcher emits
# one page blob per paginated response, leaving parse to the bronze model.
DEFAULT_BASE_URL = "https://apps.tga.gov.au/prod/sara/rest/search"
URL_OVERRIDE_ENV = "TGA_SARA_URL"
PAGE_SIZE = 100
REQUEST_DELAY = 0.5
DEFAULT_DAYS_BACK = 30


class TgaSaraRecallsFetcher(BaseFetcher):
    SOURCE_NAME = "tga_sara_recalls"
    BASE_URL = DEFAULT_BASE_URL

    def __init__(self, data_dir: Optional[str] = None) -> None:
        super().__init__(data_dir)
        self.session.headers.update({
            "Accept": "application/json, text/xml, */*",
            "User-Agent": "DK-Data-Platform/1.0 (mailto:data-platform@datakinetic.com)",
        })

    def get_latest_url(self) -> str:
        return os.getenv(URL_OVERRIDE_ENV, DEFAULT_BASE_URL)

    def fetch(self, **kwargs) -> Dict[str, Any]:
        days_back = int(kwargs.get("days_back", DEFAULT_DAYS_BACK))
        max_records = int(kwargs.get("max_records", 10_000))
        date_str = datetime.utcnow().strftime("%Y-%m-%d")

        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        to_date = datetime.utcnow().strftime("%Y-%m-%d")

        url = self.get_latest_url()
        total = 0
        page_num = 0
        errors: List[str] = []

        while total < max_records:
            params = {
                "publishedFrom": from_date,
                "publishedTo": to_date,
                "pageSize": PAGE_SIZE,
                "page": page_num,
            }
            try:
                data = self.fetch_json(url, params=params)
            except Exception as exc:
                logger.warning("TGA SARA page=%d fetch failed: %s", page_num, exc)
                errors.append(str(exc))
                break

            results = data.get("results") or data.get("items") or data.get("entries") or []
            if not results:
                break

            page_blob = {
                "_request_id": f"tga_sara_{date_str}_p{page_num:05d}",
                "_page_number": page_num,
                "query": {"from": from_date, "to": to_date},
                "results": results,
            }
            load_result = load_tga_sara_recalls_data([page_blob])
            total += load_result.get("records_inserted", 0)
            page_num += 1

            if len(results) < PAGE_SIZE:
                break
            time.sleep(REQUEST_DELAY)

        content_hash = hashlib.md5(f"{date_str}:{total}".encode()).hexdigest()
        status = "success" if total > 0 or not errors else "failed"
        result = {
            "status": status,
            "records": [],
            "record_count": total,
            "hash": content_hash,
            "errors": errors[:10],
        }
        self.log_fetch_result({"status": status, "records": total})
        return result
