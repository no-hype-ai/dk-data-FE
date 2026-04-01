"""EMA Regulatory CI Fetcher.

Feature: 011-datasource-integration
Task: Tier 4 CI source — EMA regulatory decisions

Fetches CHMP opinions, EPAR documents, and safety signals from the
European Medicines Agency open data bulk JSON export.

Data source:
  EMA publishes the full authorized medicines dataset as a bulk JSON file,
  refreshed twice daily (06:00 and 18:00 CET). ~2,641 records total.

  Bulk JSON: https://www.ema.europa.eu/en/documents/report/medicines-output-medicines_json-report_en.json

  The previously used paginated endpoint (ema.europa.eu/api/v1/medicines)
  is not an officially documented EMA API. The bulk download is the
  official data access method (ema.europa.eu/en/medicines/download-medicine-data).

Source: https://www.ema.europa.eu/en/medicines
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class EMARegulatoryCIFetcher(BaseFetcher):
    """Fetcher for EMA regulatory decisions (CI tier)."""

    SOURCE_NAME = "ema_regulatory"
    BASE_URL = "https://www.ema.europa.eu/en/medicines"

    # Official EMA bulk JSON export — all authorized medicines, updated twice daily.
    # No pagination, no rate limit, no authentication required.
    BULK_JSON_URL = (
        "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines_json-report_en.json"
    )

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

    def get_latest_url(self) -> str:
        """Get URL for the EMA bulk JSON endpoint."""
        return self.BULK_JSON_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """
        Fetch EMA regulatory decisions from the bulk JSON export.

        Downloads the full EMA authorized medicines dataset (~2,641 records)
        in a single request. This is a snapshot source — all authorized medicines
        are loaded on every run; ON CONFLICT DO UPDATE keeps records fresh.

        Keyword Args:
            days_back: Ignored for this bulk snapshot source. The EMA bulk JSON
                       contains all authorized medicines (not a change log), so
                       date filtering would drop the vast majority of records.
                       Accepted for API compatibility but has no effect.

        Returns:
            Dictionary with:
            - status: 'success' or 'failed'
            - records: List of regulatory decision dicts
            - hash: SHA-256 content hash
            - error: Error message (if failed)
        """
        days_back = None  # Bulk snapshot: always load all records

        try:
            logger.info("Fetching EMA regulatory decisions from bulk JSON (last %s days)", days_back)

            raw_items = self._fetch_bulk()
            logger.info("EMA bulk JSON: %d raw items", len(raw_items))

            # No date filter: EMA bulk JSON is a snapshot of all authorized
            # medicines (not a change log). The authorisation date for most
            # medicines is years in the past, so any incremental window would
            # drop nearly all records. Load all ~2,641 records every run;
            # ON CONFLICT (document_id) DO UPDATE handles deduplication.
            since_date: Optional[str] = None

            all_records: List[Dict[str, Any]] = []
            seen_ids: set = set()

            for item in raw_items:
                # Infer doc_type from item fields
                doc_type = self._infer_doc_type(item)

                normalised = self._normalise_record(item, doc_type)
                if not normalised:
                    continue

                # Date filter
                if since_date and normalised.get("decision_date"):
                    if normalised["decision_date"] < since_date:
                        continue

                doc_id = normalised["document_id"]
                if doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    all_records.append(normalised)

            content_hash = self._compute_hash(all_records)

            result: Dict[str, Any] = {
                "status": "success",
                "records": all_records,
                "hash": content_hash,
                "record_count": len(all_records),
            }
            self.log_fetch_result({"status": "success", "records": len(all_records)})
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

    def _fetch_bulk(self) -> List[Dict[str, Any]]:
        """Download the EMA bulk JSON file and extract the medicines list."""
        response = self.session.get(self.BULK_JSON_URL, timeout=120)
        response.raise_for_status()
        data = response.json()
        return self._extract_items(data)

    def _infer_doc_type(self, item: Dict[str, Any]) -> str:
        """Infer document type from item fields (bulk JSON has no explicit type field)."""
        category = str(item.get("category") or item.get("type") or "").lower()
        if "signal" in category or "safety" in category:
            return "safety_signal"
        if "chmp" in category or "opinion" in category:
            return "chmp_opinion"
        return "epar"

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
            for key in ("results", "data", "items", "content", "medicines", "records"):
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
            or item.get("authorisationNumber")
            or item.get("authorisation_number")
            or item.get("EmaNumber")
            or item.get("emaNumber")
        )
        if not document_id:
            return None

        document_id = str(document_id).strip()

        # Parse decision date from multiple possible fields.
        # EMA bulk JSON uses camelCase; older API uses snake_case.
        decision_date = (
            item.get("decision_date")
            or item.get("date")
            or item.get("revision_date")
            or item.get("authorisationDate")
            or item.get("dateFirstAuthorised")
            or item.get("opinionDate")
            or item.get("marketingAuthorisationDate")
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
            "product_name": (
                item.get("product_name")
                or item.get("name")
                or item.get("medicineName")
                or item.get("brandName")
            ),
            "active_substance": (
                item.get("active_substance")
                or item.get("inn")
                or item.get("active_ingredients")
                or item.get("activeSubstance")
                or item.get("internationalNonproprietaryName")
            ),
            "therapeutic_area": (
                item.get("therapeutic_area")
                or item.get("atc_code")
                or item.get("therapeuticArea")
                or item.get("atcCode")
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
