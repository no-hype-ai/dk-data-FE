"""OpenFDA Drug Labels Fetcher.

Fetches drug label (SPL) records from the FDA openFDA API.
Results are stored as page-level JSONB blobs in mol_raw.openfda_labels —
each raw row contains a ``results`` array of up to PAGE_SIZE labels.

The bronze model (mol_bronze.openfda_labels) unnests the results array
using ``jsonb_array_elements(response_body->'results')``.

API Docs: https://open.fda.gov/apis/drug/label/
Rate limit: 1000 req/min (with API key); 40 req/min (anonymous)
Max records per search: 25 000 (skip + limit ≤ 25 000)
"""

import hashlib
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

BASE_URL = "https://api.fda.gov/drug/label.json"

# FDA openFDA API hard cap per page
PAGE_SIZE = 100

# FDA limits total accessible records to 25 000 per search query
FDA_SKIP_LIMIT = 25_000

# Default cap per run
DEFAULT_MAX_RECORDS = 5_000

# Polite delay between pages
REQUEST_DELAY = 0.1


class OpenFDALabelsFetcher(BaseFetcher):
    """Fetcher for FDA drug label (SPL) data via openFDA.

    Pages through the /drug/label endpoint and returns one dict per page,
    each containing a ``results`` list (matching the API response shape
    expected by mol_bronze.openfda_labels).
    """

    SOURCE_NAME = "openfda_labels"
    BASE_URL = BASE_URL

    def __init__(self, data_dir: Optional[str] = None) -> None:
        super().__init__(data_dir)
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "DK-Data-Platform/1.0 (mailto:data-platform@datakinetic.com)",
        })

    def get_latest_url(self) -> str:
        return BASE_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch drug label records from openFDA.

        Keyword Args:
            days_back: Restrict to labels with effective_time updated in the
                last N days. Defaults to 90 (labels change infrequently).
            max_records: Maximum label records to fetch. Defaults to 5000.
                Capped at FDA_SKIP_LIMIT (25 000) per query.
            search: Raw openFDA search query string. If provided, overrides
                the date-based filter.

        Returns:
            Dict with keys: status, records, record_count, hash.
            ``records`` is a list of page blobs (each with a ``results`` key),
            not individual labels — the loader inserts one raw row per page.
        """
        days_back: int = int(kwargs.get("days_back", 90))
        max_records: int = min(
            int(kwargs.get("max_records", DEFAULT_MAX_RECORDS)),
            FDA_SKIP_LIMIT,
        )
        search: Optional[str] = kwargs.get("search")

        try:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")

            if not search:
                from_date = (
                    datetime.utcnow() - timedelta(days=days_back)
                ).strftime("%Y%m%d")
                # openFDA Lucene range query; requests will URL-encode the brackets
                # Use a literal string and pass via the URL to avoid double-encoding
                search = f"effective_time:[{from_date} TO 99991231]"

            page_blobs, total_labels = self._paginate(
                search=search,
                max_records=max_records,
                date_str=date_str,
            )

            content_hash = hashlib.md5(
                f"{date_str}:{total_labels}".encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": page_blobs,
                "record_count": len(page_blobs),
                "hash": content_hash,
                "_total_labels": total_labels,
            }
            self.log_fetch_result({"status": "success", "records": len(page_blobs)})
            return result

        except Exception as exc:
            logger.exception("OpenFDA Labels fetch failed: %s", exc)
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
        search: str,
        max_records: int,
        date_str: str,
    ) -> tuple:
        """Page through the openFDA drug/label endpoint.

        Returns:
            Tuple of (page_blobs, total_labels_fetched).
        """
        page_blobs: List[Dict[str, Any]] = []
        total_labels = 0
        page_num = 0

        while total_labels < max_records:
            skip = total_labels
            if skip >= FDA_SKIP_LIMIT:
                logger.info(
                    "OpenFDA Labels: reached FDA skip limit (%d), stopping", FDA_SKIP_LIMIT
                )
                break

            remaining = max_records - total_labels
            limit = min(PAGE_SIZE, remaining, FDA_SKIP_LIMIT - skip)

            params: Dict[str, Any] = {
                "search": search,
                "limit": limit,
                "skip": skip,
            }

            try:
                data = self.fetch_json(BASE_URL, params=params)
            except Exception as exc:
                logger.warning(
                    "OpenFDA Labels page skip=%d fetch failed: %s", skip, exc
                )
                break

            results = data.get("results", [])
            if not results:
                break

            page_blob = {
                "_request_id": f"fda_labels_{date_str}_skip{skip:07d}",
                "_page_number": page_num,
                "results": results,
            }
            page_blobs.append(page_blob)
            total_labels += len(results)
            page_num += 1

            logger.info(
                "OpenFDA Labels: page %d (skip=%d) fetched %d labels (total: %d)",
                page_num - 1, skip, len(results), total_labels,
            )

            # Stop if we got fewer than requested (last page)
            if len(results) < limit:
                break

            time.sleep(REQUEST_DELAY)

        logger.info(
            "OpenFDA Labels pagination complete: %d pages, %d labels",
            len(page_blobs), total_labels,
        )
        return page_blobs, total_labels
