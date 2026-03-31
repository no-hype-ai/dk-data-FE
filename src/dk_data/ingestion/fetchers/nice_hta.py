"""NICE HTA fetcher — NICE Technology Appraisals and guidance documents.

Fetches guidance records from the NICE (National Institute for Health
and Care Excellence) public API. NICE technology appraisals (TAs) are the
authoritative UK HTA assessments for pharmaceutical and medical technology
reimbursement decisions.

API: https://api.nice.org.uk/services/guidance
  Public, no authentication required.
  Endpoint: GET /published?type={TYPE}&page={N}&pageSize=100
  Response: {"Data": [{Id, Title, GuidanceType, PublishedDate, ...}], "Total": N}
  Guidance types fetched: TA, HST, IPG, MTA

Total: ~650 technology appraisals + ~500 other guidance = ~1,200 records.

Stores one JSONB record per guidance document in mol_raw.nice_hta.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.nice.org.uk/services/guidance"
_PAGE_SIZE = 100
_REQUEST_DELAY = 0.5
_DEFAULT_MAX_RECORDS = 5_000
# Guidance types: TA=Technology Appraisal, HST=Highly Specialised Technology,
# IPG=Interventional Procedures, MTA=Medical Technology
_GUIDANCE_TYPES = ["TA", "HST", "IPG", "MTA"]


class NICEHTAFetcher(BaseFetcher):
    """Fetcher for NICE guidance documents via the NICE public API.

    Paginates through guidance documents for each guidance type. Each record
    is a guidance dict keyed by Id (NICE guidance ID integer).
    Deduplication at load time uses an expression index on
    response_body->>'Id'.
    """

    SOURCE_NAME = "nice_hta"
    BASE_URL = _BASE_URL

    def get_latest_url(self) -> str:
        return f"{_BASE_URL}/published?type=TA&page=1&pageSize={_PAGE_SIZE}"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch NICE guidance records across all HTA-relevant guidance types.

        Keyword Args:
            max_records: Cap total records across all types. Default: 5,000.
            guidance_types: List of types to fetch. Default: TA, HST, IPG, MTA.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: int = int(kwargs.get("max_records", _DEFAULT_MAX_RECORDS))
        guidance_types: List[str] = list(
            kwargs.get("guidance_types", _GUIDANCE_TYPES)
        )

        try:
            records = self._fetch_all_types(
                guidance_types=guidance_types,
                max_records=max_records,
            )
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
            logger.exception("NICE HTA fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_all_types(
        self, guidance_types: List[str], max_records: int
    ) -> List[Dict[str, Any]]:
        """Fetch guidance records for each specified guidance type."""
        seen_ids: set = set()
        all_records: List[Dict[str, Any]] = []

        for guidance_type in guidance_types:
            if len(all_records) >= max_records:
                break
            remaining = max_records - len(all_records)
            type_records = self._fetch_guidance_type(
                guidance_type=guidance_type,
                max_records=remaining,
            )
            added = 0
            for rec in type_records:
                doc_id = rec.get("Id")
                if doc_id and doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    all_records.append(rec)
                    added += 1
            logger.info(
                "NICE HTA: type=%s → %d new records (running total=%d)",
                guidance_type, added, len(all_records),
            )

        logger.info("NICE HTA: %d total guidance records fetched", len(all_records))
        return all_records

    def _fetch_guidance_type(
        self, guidance_type: str, max_records: int
    ) -> List[Dict[str, Any]]:
        """Paginate through a single NICE guidance type."""
        all_records: List[Dict[str, Any]] = []
        page = 1
        total_pages: Optional[int] = None

        while len(all_records) < max_records:
            params: Dict[str, Any] = {
                "type": guidance_type,
                "page": page,
                "pageSize": _PAGE_SIZE,
            }

            logger.debug("NICE HTA: type=%s page=%d", guidance_type, page)

            try:
                resp = self.session.get(
                    f"{_BASE_URL}/published",
                    params=params,
                    timeout=30,
                )
                if resp.status_code == 404:
                    break
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning(
                    "NICE HTA request failed for type=%s page=%d: %s",
                    guidance_type, page, exc,
                )
                break

            if total_pages is None:
                total = data.get("Total", 0)
                total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
                logger.info(
                    "NICE HTA: type=%s total=%d pages=%d",
                    guidance_type, total, total_pages,
                )

            guidance_list = data.get("Data", [])
            if not guidance_list:
                break

            # Tag each record with its guidance type for routing
            for item in guidance_list:
                item["_guidance_type"] = guidance_type

            all_records.extend(guidance_list)

            if page >= total_pages:
                break

            page += 1
            time.sleep(_REQUEST_DELAY)

        return all_records
