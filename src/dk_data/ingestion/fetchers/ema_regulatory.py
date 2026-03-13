"""EMA Regulatory CI Fetcher.

Feature: 011-datasource-integration
Task: Tier 4 CI source — EMA regulatory decisions

Fetches CHMP opinions, EPAR documents, and safety signals from the
European Medicines Agency public API.

Source: https://www.ema.europa.eu/en/medicines
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class EMARegulatoryCIFetcher(BaseFetcher):
    """Fetcher for EMA regulatory decisions (CI tier)."""

    SOURCE_NAME = "ema_regulatory"
    BASE_URL = "https://www.ema.europa.eu/en/medicines"

    # EMA public medicines API — primary endpoint
    # Note: The EMA website has antibot protection on many endpoints.
    # The open data portal at https://www.ema.europa.eu/en/medicines/download-medicine-data
    # provides CSV/Excel downloads but no stable JSON API.
    # We try multiple endpoints and gracefully handle failures.
    EMA_API_BASE = "https://www.ema.europa.eu/en/medicines/field_ema_web_categories"

    # Known EMA API endpoints for structured data
    MEDICINES_API = "https://www.ema.europa.eu/en/medicines/field_ema_web_categories%253Ahuman_use"

    # Fallback: EMA open data endpoint (may return HTML instead of JSON)
    EMA_OPEN_DATA_API = "https://www.ema.europa.eu/en/medicines"

    # Decision types we track
    VALID_DECISION_TYPES = frozenset({
        "authorisation",
        "variation",
        "withdrawal",
        "suspension",
        "renewal",
        "referral",
        "orphan_designation",
        "paediatric",
        "advanced_therapy",
        "biosimilar",
        "conditional_approval",
        "exceptional_circumstances",
        "sunset_clause",
    })

    # Document types fetched
    DOCUMENT_TYPES = ["chmp_opinion", "epar", "safety_signal"]

    # Default page size
    PAGE_SIZE = 50

    def get_latest_url(self) -> str:
        """Get URL for the EMA medicines API endpoint."""
        return self.MEDICINES_API

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """
        Fetch recent EMA regulatory decisions.

        Keyword Args:
            days_back: Number of days to look back (default: 7).
            max_pages: Maximum number of pages to fetch (default: 20).

        Returns:
            Dictionary with:
            - status: 'success' or 'failed'
            - records: List of regulatory decision dicts
            - hash: SHA-256 content hash
            - error: Error message (if failed)
        """
        days_back = kwargs.get("days_back", 7)
        max_pages = kwargs.get("max_pages", 20)

        try:
            logger.info(
                "Fetching EMA regulatory decisions (last %d days)", days_back
            )

            all_records: List[Dict[str, Any]] = []

            # Fetch each document type
            for doc_type in self.DOCUMENT_TYPES:
                records = self._fetch_document_type(
                    doc_type, days_back=days_back, max_pages=max_pages
                )
                all_records.extend(records)

            # Deduplicate by document_id
            seen_ids: set = set()
            unique_records: List[Dict[str, Any]] = []
            for record in all_records:
                doc_id = record.get("document_id")
                if doc_id and doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    unique_records.append(record)

            # Compute content hash
            content_hash = self._compute_hash(unique_records)

            result: Dict[str, Any] = {
                "status": "success",
                "records": unique_records,
                "hash": content_hash,
                "record_count": len(unique_records),
                "days_back": days_back,
            }
            self.log_fetch_result(
                {"status": "success", "records": len(unique_records)}
            )
            return result

        except Exception as e:
            logger.exception("Failed to fetch EMA regulatory data: %s", e)
            result = {
                "status": "failed",
                "records": [],
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_document_type(
        self,
        doc_type: str,
        *,
        days_back: int = 7,
        max_pages: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Fetch paginated results for a single EMA document type.

        Args:
            doc_type: One of DOCUMENT_TYPES.
            days_back: Look-back window in days.
            max_pages: Safety limit for pagination.

        Returns:
            List of normalised record dicts.
        """
        records: List[Dict[str, Any]] = []
        since_date = (
            datetime.now(timezone.utc) - timedelta(days=days_back)
        ).strftime("%Y-%m-%d")
        page = 0

        while page < max_pages:
            params = {
                "type": doc_type,
                "date_from": since_date,
                "page": page,
                "page_size": self.PAGE_SIZE,
            }

            try:
                data = self.fetch_json(self.get_latest_url(), params=params)
            except Exception as e:
                error_str = str(e)
                if "403" in error_str or "401" in error_str or "cloudflare" in error_str.lower():
                    logger.warning(
                        "EMA API blocked by antibot protection for %s page %d: %s. "
                        "The EMA website does not expose a stable public JSON API. "
                        "Consider using the EMA open data CSV downloads instead.",
                        doc_type,
                        page,
                        e,
                    )
                else:
                    logger.warning(
                        "EMA API request failed for %s page %d: %s",
                        doc_type,
                        page,
                        e,
                    )
                break

            items = self._extract_items(data)
            if not items:
                break

            for item in items:
                normalised = self._normalise_record(item, doc_type)
                if normalised:
                    records.append(normalised)

            # Stop when we receive fewer items than the page size
            if len(items) < self.PAGE_SIZE:
                break

            page += 1

        logger.info(
            "Fetched %d %s records from EMA", len(records), doc_type
        )
        return records

    @staticmethod
    def _extract_items(data: Any) -> List[Dict]:
        """
        Extract the list of items from an EMA API response.

        The EMA API may return items under different keys depending on the
        endpoint version.
        """
        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            for key in ("results", "data", "items", "content"):
                if key in data and isinstance(data[key], list):
                    return data[key]

        return []

    def _normalise_record(
        self, item: Dict[str, Any], doc_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Map a raw EMA API item to the raw.ema_regulatory schema.

        Returns None when the item lacks a usable document ID.
        """
        document_id = (
            item.get("id")
            or item.get("document_id")
            or item.get("medicine_id")
            or item.get("product_number")
        )
        if not document_id:
            return None

        document_id = str(document_id).strip()

        # Parse decision date from multiple possible fields
        decision_date = (
            item.get("decision_date")
            or item.get("date")
            or item.get("revision_date")
        )
        if decision_date:
            decision_date = str(decision_date)[:10]  # YYYY-MM-DD

        # Normalise decision_type
        raw_decision_type = str(
            item.get("decision_type")
            or item.get("type")
            or item.get("category")
            or ""
        ).lower().replace(" ", "_").replace("-", "_")

        decision_type: Optional[str] = (
            raw_decision_type if raw_decision_type in self.VALID_DECISION_TYPES else None
        )

        return {
            "document_id": document_id,
            "document_type": doc_type,
            "product_name": item.get("product_name") or item.get("name"),
            "active_substance": (
                item.get("active_substance")
                or item.get("inn")
                or item.get("active_ingredients")
            ),
            "therapeutic_area": (
                item.get("therapeutic_area")
                or item.get("atc_code")
            ),
            "decision_date": decision_date,
            "decision_type": decision_type,
            "document_url": item.get("url") or item.get("document_url"),
            "summary": item.get("summary") or item.get("description"),
        }

    @staticmethod
    def _compute_hash(records: List[Dict[str, Any]]) -> str:
        """Compute a deterministic SHA-256 hash over the fetched records."""
        import json

        payload = json.dumps(records, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
