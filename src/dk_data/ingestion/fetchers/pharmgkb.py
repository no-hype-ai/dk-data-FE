"""PharmGKB REST API fetcher — paginated chemical and gene entity bulk download.

Feature: 019-cms-puf-platform-reconciliation

PharmGKB provides pharmacogenomics data (drug-gene associations, clinical
annotations, dosing guidelines, variant annotations) via a public REST API.
Authentication is optional: unauthenticated requests work but are rate-limited.

API base: https://api.pharmgkb.org/v1
Credentials: PHARMGKB_API_KEY env var (optional).
  If set, sent as an Authorization header on every request.

Pagination strategy:
  GET /data/chemical?view=max&pageSize=100&page=N
  GET /data/gene?view=max&pageSize=100&page=N
  Increment `page` (1-based) until the response `data` array is empty or the
  safety cap (max_pages=200) is reached.

Each page response dict is stored as one record in the output so that the
downstream loader can persist full raw pages to mol_raw.pharmgkb.
"""

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

BASE_URL = "https://api.pharmgkb.org/v1"
PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 200
PAGE_DELAY_SECONDS = 0.2


class PharmGKBFetcher(BaseFetcher):
    """Fetcher for PharmGKB chemical and gene entity data."""

    SOURCE_NAME = "pharmgkb"
    BASE_URL = BASE_URL

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)
        api_key = os.environ.get("PHARMGKB_API_KEY", "")
        if api_key:
            self.session.headers.update({"Authorization": api_key})
            logger.info("PharmGKB API key loaded from PHARMGKB_API_KEY")
        else:
            logger.info(
                "PHARMGKB_API_KEY not set — using public (rate-limited) access"
            )
        self.session.headers.update({"Accept": "application/json"})

    def get_latest_url(self) -> str:
        return f"{BASE_URL}/data/chemical?view=max&pageSize={PAGE_SIZE}&page=1"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch PharmGKB entities by paginating through the bulk data endpoint.

        Keyword Args:
            entity_type: "chemical" (default) or "gene".
            max_pages:   Safety cap on pages fetched (default 200).

        Returns:
            Dict with keys:
                status        — "success" or "failed"
                records       — list of raw page response dicts (one per page)
                record_count  — len(records)
                hash          — MD5 of all pharmgkb IDs seen
                entity_type   — echoed back from kwargs
                error         — present only on failure
        """
        entity_type: str = kwargs.get("entity_type", "chemical")
        max_pages: int = int(kwargs.get("max_pages", DEFAULT_MAX_PAGES))

        page_records: List[Dict[str, Any]] = []

        try:
            for page_num in range(1, max_pages + 1):
                url = (
                    f"{BASE_URL}/data/{entity_type}"
                    f"?view=max&pageSize={PAGE_SIZE}&page={page_num}"
                )
                logger.debug(
                    "PharmGKB fetching %s page %d/%d", entity_type, page_num, max_pages
                )

                try:
                    resp = self.session.get(url, timeout=60)
                    resp.raise_for_status()
                    page_data = resp.json()
                except Exception as exc:
                    logger.error(
                        "PharmGKB request failed at %s page %d: %s",
                        entity_type, page_num, exc,
                    )
                    return {
                        "status": "failed",
                        "records": page_records,
                        "record_count": len(page_records),
                        "hash": None,
                        "entity_type": entity_type,
                        "error": str(exc),
                    }

                items: List[Any] = page_data.get("data", [])
                if not items:
                    logger.info(
                        "PharmGKB %s: empty data on page %d — pagination complete",
                        entity_type, page_num,
                    )
                    break

                # Annotate the page dict with metadata for downstream loaders
                page_data["_page_num"] = page_num
                page_data["_entity_type"] = entity_type
                page_records.append(page_data)

                logger.debug(
                    "PharmGKB %s page %d: %d items", entity_type, page_num, len(items)
                )

                if page_num < max_pages:
                    time.sleep(PAGE_DELAY_SECONDS)

            total_items = sum(len(p.get("data", [])) for p in page_records)
            logger.info(
                "PharmGKB %s fetch complete: %d pages, %d total items",
                entity_type, len(page_records), total_items,
            )

            # Hash over all entity IDs for change detection
            all_ids: List[str] = [
                str(item.get("id") or item.get("pharmgkbId", ""))
                for page in page_records
                for item in page.get("data", [])
            ]
            content_hash = hashlib.md5(
                json.dumps(sorted(all_ids), sort_keys=True).encode()
            ).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": page_records,
                "record_count": len(page_records),
                "hash": content_hash,
                "entity_type": entity_type,
            }
            self.log_fetch_result({"status": "success", "records": len(page_records)})
            return result

        except Exception as exc:
            logger.exception("PharmGKB fetch failed unexpectedly: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "entity_type": entity_type,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result
