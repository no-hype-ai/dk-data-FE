"""Reactome fetcher — human biological pathway data.

Fetches pathway records from the Reactome ContentService API. Reactome is
the authoritative curated database of human biological pathways and
reactions.

Strategy:
  1. GET top-level human pathways (taxId=9606) from /data/pathways/top/9606
  2. For each top-level pathway, fetch contained sub-events recursively via
     /data/pathway/{stId}/containedEvents
  3. Dedup by stId (Reactome stable identifier, e.g. R-HSA-1234567)

API: https://reactome.org/ContentService
  Public, no authentication required.
  Rate limit: ~5 requests/second.
  Total human pathways: ~20,000.

Stores one JSONB record per pathway in mol_raw.reactome.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_CONTENT_URL = "https://reactome.org/ContentService"
_REQUEST_DELAY = 0.2
_DEFAULT_MAX_RECORDS = 25_000
_HUMAN_TAX_ID = 9606


class ReactomeFetcher(BaseFetcher):
    """Fetcher for Reactome human pathway data via the ContentService API.

    Fetches top-level human pathways then recursively expands each pathway's
    contained events. Each record is a pathway dict keyed by stId.
    Deduplication at load time uses an expression index on
    response_body->>'stId'.
    """

    SOURCE_NAME = "reactome"
    BASE_URL = _CONTENT_URL

    def get_latest_url(self) -> str:
        return f"{_CONTENT_URL}/data/pathways/top/{_HUMAN_TAX_ID}"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch Reactome human pathway records.

        Keyword Args:
            max_records: Cap total pathway records. Default: 25,000.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: int = int(kwargs.get("max_records", _DEFAULT_MAX_RECORDS))

        try:
            records = self._fetch_all_pathways(max_records=max_records)
            content_hash = hashlib.md5(
                json.dumps(len(records)).encode()
            ).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("Reactome fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_all_pathways(self, max_records: int) -> List[Dict[str, Any]]:
        """Fetch top-level pathways and recursively expand contained events."""
        seen: Set[str] = set()
        all_records: List[Dict[str, Any]] = []

        # Step 1: fetch top-level human pathways
        top_url = f"{_CONTENT_URL}/data/pathways/top/{_HUMAN_TAX_ID}"
        logger.info("Reactome: fetching top-level human pathways")
        try:
            resp = self.session.get(top_url, timeout=60)
            resp.raise_for_status()
            top_pathways: List[Dict[str, Any]] = resp.json()
        except Exception as exc:
            logger.error("Reactome: failed to fetch top-level pathways: %s", exc)
            return []

        logger.info("Reactome: %d top-level pathways found", len(top_pathways))

        # Step 2: add top-level pathways and expand children
        queue: List[Dict[str, Any]] = list(top_pathways)

        while queue and len(all_records) < max_records:
            pathway = queue.pop(0)
            st_id = pathway.get("stId")
            if not st_id or st_id in seen:
                continue

            seen.add(st_id)
            all_records.append(pathway)

            if len(all_records) >= max_records:
                break

            # Fetch contained sub-events for this pathway
            contained_url = f"{_CONTENT_URL}/data/pathway/{st_id}/containedEvents"
            try:
                resp = self.session.get(contained_url, timeout=30)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                contained: List[Dict[str, Any]] = resp.json()
                # Only add pathway-type sub-events to avoid reactions/complexes
                for event in contained:
                    if event.get("stId") and event.get("stId") not in seen:
                        if event.get("className") in (
                            "Pathway", "TopLevelPathway", "BlackBoxEvent"
                        ) or "Pathway" in str(event.get("className", "")):
                            queue.append(event)
            except Exception as exc:
                logger.debug(
                    "Reactome: failed to fetch contained events for %s: %s",
                    st_id, exc,
                )

            time.sleep(_REQUEST_DELAY)

            if len(all_records) % 500 == 0:
                logger.info(
                    "Reactome: %d pathways collected so far", len(all_records)
                )

        logger.info("Reactome: %d total pathway records fetched", len(all_records))
        return all_records
