"""CMS Medicare Coverage API fetcher.

Feature: 021-post-deploy-fixes

Fetches National Coverage Determinations (NCDs), National Coverage Analyses
(NCAs), and Technology Assessments from the CMS Medicare Coverage Database
API. This is the US equivalent of NICE HTA — authoritative Medicare coverage
policy decisions for drugs, devices, and medical services.

API: https://api.coverage.cms.gov/v1/data/
  Public REST API, no authentication required for NCD/NCA/TA endpoints.
  Endpoints fetched:
    - /v1/data/ncd/                  → National Coverage Determinations
    - /v1/data/nca/                  → National Coverage Analyses
    - /v1/data/technology-assessment/ → Technology Assessments

Total expected: ~1,800 NCDs, ~400 NCAs, ~200 TAs ≈ 2,400 records.

Stores one JSONB record per decision in mol_raw.cms_coverage, tagged with
_endpoint for deduplication across coverage types.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.coverage.cms.gov/v1"
_PAGE_SIZE = 100
_REQUEST_DELAY = 0.3  # CMS asks for respectful access

_ENDPOINTS = [
    ("ncd", "/data/ncd/"),
    ("nca", "/data/nca/"),
    ("technology_assessment", "/data/technology-assessment/"),
]

_DEFAULT_MAX_RECORDS = 10_000


class CMSCoverageFetcher(BaseFetcher):
    """Fetcher for CMS Medicare Coverage Database decisions."""

    SOURCE_NAME = "cms_coverage"
    BASE_URL = _BASE_URL

    def get_latest_url(self) -> str:
        return f"{_BASE_URL}/data/ncd/"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch all CMS coverage decisions (NCDs, NCAs, Technology Assessments).

        Keyword Args:
            max_records: Cap on total records fetched (default: 10,000).
            endpoints: List of (name, path) tuples to fetch (default: all three).

        Returns:
            Dict with status, records, record_count, hash.
        """
        max_records: int = int(kwargs.get("max_records", _DEFAULT_MAX_RECORDS))
        endpoints = kwargs.get("endpoints", _ENDPOINTS)

        try:
            records = self._fetch_all_endpoints(endpoints=endpoints, max_records=max_records)
            content_hash = hashlib.md5(
                json.dumps(sorted(
                    f"{r.get('id', '')}:{r.get('_endpoint', '')}" for r in records
                )).encode()
            ).hexdigest()
            result = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("CMS Coverage fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_all_endpoints(
        self,
        endpoints: List[tuple],
        max_records: int,
    ) -> List[Dict[str, Any]]:
        """Fetch and combine records from all configured endpoints."""
        seen_keys: set = set()
        all_records: List[Dict[str, Any]] = []

        for endpoint_name, endpoint_path in endpoints:
            if len(all_records) >= max_records:
                break
            remaining = max_records - len(all_records)
            endpoint_records = self._fetch_endpoint(
                endpoint_name=endpoint_name,
                endpoint_path=endpoint_path,
                max_records=remaining,
            )
            added = 0
            for rec in endpoint_records:
                key = (str(rec.get("id", "")), endpoint_name)
                if key not in seen_keys:
                    seen_keys.add(key)
                    rec["_endpoint"] = endpoint_name
                    all_records.append(rec)
                    added += 1

            logger.info(
                "CMS Coverage: endpoint=%s → %d new records (total=%d)",
                endpoint_name, added, len(all_records),
            )

        logger.info("CMS Coverage: %d total records fetched", len(all_records))
        return all_records

    def _fetch_endpoint(
        self,
        endpoint_name: str,
        endpoint_path: str,
        max_records: int,
    ) -> List[Dict[str, Any]]:
        """Paginate through a single CMS Coverage API endpoint."""
        all_records: List[Dict[str, Any]] = []
        page = 1
        total_pages: Optional[int] = None
        url = f"{_BASE_URL}{endpoint_path}"

        while len(all_records) < max_records:
            params = {"page": page, "pageSize": _PAGE_SIZE}
            logger.debug("CMS Coverage: endpoint=%s page=%d", endpoint_name, page)

            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 404:
                    logger.warning("CMS Coverage endpoint not found: %s", url)
                    break
                if resp.status_code in (401, 403):
                    logger.warning(
                        "CMS Coverage endpoint %s returned %d — may require license token. "
                        "See https://api.coverage.cms.gov/docs/ for auth details.",
                        endpoint_name, resp.status_code,
                    )
                    break
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning(
                    "CMS Coverage request failed for endpoint=%s page=%d: %s",
                    endpoint_name, page, exc,
                )
                break

            # Extract records — API returns either a list or {data: [...], meta: {...}}
            records, total = self._extract_records(data)

            if total_pages is None and total is not None:
                total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
                logger.info(
                    "CMS Coverage: endpoint=%s total=%d pages=%d",
                    endpoint_name, total, total_pages,
                )

            if not records:
                break

            all_records.extend(records)

            last_page = (total_pages is not None and page >= total_pages)
            if last_page or len(records) < _PAGE_SIZE:
                break

            page += 1
            time.sleep(_REQUEST_DELAY)

        return all_records

    @staticmethod
    def _extract_records(data: Any) -> tuple[List[Dict], Optional[int]]:
        """Extract records list and total count from API response.

        Handles three response shapes:
        - Plain list: [{...}, ...]
        - Wrapped: {"data": [...], "meta": {"total": N}}
        - Wrapped: {"results": [...], "count": N}
        """
        if isinstance(data, list):
            return data, len(data)

        if isinstance(data, dict):
            for data_key in ("data", "results", "items", "records"):
                if data_key in data and isinstance(data[data_key], list):
                    records = data[data_key]
                    # Try to find total from common meta patterns
                    total = (
                        data.get("meta", {}).get("total")
                        or data.get("total")
                        or data.get("count")
                        or data.get("totalCount")
                    )
                    return records, total

        return [], None
