"""FDA Drug Shortages fetcher — current and resolved US drug shortages.

Fetches drug shortage data from the openFDA /drug/shortages endpoint.
Results are stored as page-level JSONB blobs in mol_raw.fda_shortages —
each raw row contains a ``results`` array of up to PAGE_SIZE entries.

The bronze model (mol_bronze.fda_shortages) unnests the results array
using ``jsonb_array_elements(response_body->'results')``.

API Docs: https://open.fda.gov/apis/drug/shortages/
Rate limit: 240 req/min with API key, 40 without.
Max records per search: 25,000 (skip + limit <= 25,000).

This endpoint is relatively small (~1.5k total records), so the fetcher
pulls the full dataset on each weekly run rather than date-filtering.
"""

import hashlib
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseFetcher
from ..sources.fda_shortages import load_fda_shortages_data

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.fda.gov/drug/shortages.json"
_PAGE_SIZE = 1000
_FDA_SKIP_LIMIT = 25_000
_OPENFDA_API_KEY: Optional[str] = os.getenv("OPENFDA_API_KEY") or None
_REQUEST_DELAY = 0.3


class FDAShortagesFetcher(BaseFetcher):
    """Fetcher for FDA drug shortage data via openFDA.

    Pages through the /drug/shortages endpoint and returns one dict per page,
    each containing a ``results`` list (matching the API response shape
    expected by mol_bronze.fda_shortages).

    The shortages dataset is small (~1.5k records), so each weekly run
    fetches the full dataset. Deduplication at the loader level via
    response_body_hash prevents duplicate page insertion.
    """

    SOURCE_NAME = "fda_shortages"
    BASE_URL = "https://api.fda.gov"

    def __init__(self, data_dir: Optional[str] = None) -> None:
        super().__init__(data_dir)
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "DK-Data-Platform/1.0 (mailto:data-platform@datakinetic.com)",
        })

    def get_latest_url(self) -> str:
        return _BASE_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch FDA drug shortage records from openFDA.

        Keyword Args:
            max_records: Maximum records to fetch (max 25,000).
                Defaults to 25,000 (full dataset).

        Returns:
            Dict with keys: status, records, record_count, hash.
            ``records`` is a list of page blobs (each with a ``results`` key),
            not individual reports -- the loader inserts one raw row per page.
        """
        try:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")
            max_records: int = min(
                int(kwargs.get("max_records", _FDA_SKIP_LIMIT)),
                _FDA_SKIP_LIMIT,
            )

            page_blobs, total_reports = self._paginate(
                max_records=max_records,
                date_str=date_str,
            )

            # Stream pages to DB
            if page_blobs:
                load_fda_shortages_data(page_blobs)

            content_hash = hashlib.md5(
                f"{date_str}:{total_reports}".encode()
            ).hexdigest()
            result: Dict[str, Any] = {
                "status": "success",
                "records": [],  # already loaded to DB
                "record_count": total_reports,
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": total_reports})
            return result

        except Exception as exc:
            logger.exception("FDA shortages fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _paginate(
        self,
        max_records: int,
        date_str: str,
        search: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Page through the openFDA /drug/shortages endpoint.

        Returns:
            Tuple of (page_blobs, total_reports_fetched).
        """
        page_blobs: List[Dict[str, Any]] = []
        total_reports = 0
        page_num = 0

        while total_reports < max_records:
            skip = total_reports
            if skip >= _FDA_SKIP_LIMIT:
                logger.info(
                    "FDA shortages: reached FDA skip limit (%d), stopping",
                    _FDA_SKIP_LIMIT,
                )
                break

            remaining = max_records - total_reports
            limit = min(_PAGE_SIZE, remaining, _FDA_SKIP_LIMIT - skip)

            params: Dict[str, Any] = {
                "limit": limit,
                "skip": skip,
            }
            if search:
                params["search"] = search
            if _OPENFDA_API_KEY:
                params["api_key"] = _OPENFDA_API_KEY

            try:
                data = self.fetch_json(_BASE_URL, params=params)
            except Exception as exc:
                logger.warning(
                    "FDA shortages page skip=%d fetch failed: %s", skip, exc
                )
                break

            results = data.get("results", [])
            if not results:
                break

            page_blob = {
                "_request_id": f"shortages_{date_str}_skip{skip:07d}",
                "_page_number": page_num,
                "results": results,
            }
            page_blobs.append(page_blob)
            total_reports += len(results)
            page_num += 1

            logger.info(
                "FDA shortages: page %d (skip=%d) fetched %d entries (total: %d)",
                page_num - 1,
                skip,
                len(results),
                total_reports,
            )

            if len(results) < limit:
                break

            time.sleep(_REQUEST_DELAY)

        logger.info(
            "FDA shortages pagination complete: %d pages, %d entries",
            len(page_blobs),
            total_reports,
        )
        return page_blobs, total_reports
