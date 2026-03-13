"""EMA Regulatory CI Fetcher.

Feature: 011-datasource-integration
Task: Tier 4 CI source — EMA regulatory decisions

Fetches medicines data from the European Medicines Agency official
JSON data files (updated twice daily at 06:00 and 18:00 CET).

The EMA website has antibot protection on its HTML pages, so we use
the official bulk JSON data endpoints instead.

Sources:
- Medicines: https://www.ema.europa.eu/en/documents/report/medicines-output-medicines_json-report_en.json
- Safety (DHPC): https://www.ema.europa.eu/en/documents/report/dhpc-output-json-report_en.json
- Orphan designations: https://www.ema.europa.eu/en/documents/report/medicines-output-orphan_designations-json-report_en.json
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Official EMA JSON data file URLs (bulk dumps, updated twice daily)
EMA_MEDICINES_JSON = (
    "https://www.ema.europa.eu/en/documents/report/"
    "medicines-output-medicines_json-report_en.json"
)
EMA_SAFETY_JSON = (
    "https://www.ema.europa.eu/en/documents/report/"
    "dhpc-output-json-report_en.json"
)
EMA_ORPHAN_JSON = (
    "https://www.ema.europa.eu/en/documents/report/"
    "medicines-output-orphan_designations-json-report_en.json"
)


class EMARegulatoryCIFetcher(BaseFetcher):
    """Fetcher for EMA regulatory decisions (CI tier)."""

    SOURCE_NAME = "ema_regulatory"
    BASE_URL = "https://www.ema.europa.eu"

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

    def get_latest_url(self) -> str:
        """Get URL for the EMA medicines JSON data file."""
        return EMA_MEDICINES_JSON

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch recent EMA regulatory decisions from official JSON data files.

        Keyword Args:
            days_back: Number of days to look back (default: 90).
            max_records: Optional cap on returned records.

        Returns:
            Dictionary with status, records, hash, error.
        """
        days_back = kwargs.get("days_back", 90)
        max_records: Optional[int] = kwargs.get("max_records") or self.params.get("max_records")

        try:
            logger.info(
                "Fetching EMA regulatory decisions (last %d days)", days_back
            )

            all_records: List[Dict[str, Any]] = []

            # Fetch medicines data (CHMP opinions + EPARs)
            medicines_records = self._fetch_medicines_json(days_back=days_back)
            all_records.extend(medicines_records)

            # Fetch safety signals (DHPC)
            safety_records = self._fetch_safety_json(days_back=days_back)
            all_records.extend(safety_records)

            # Deduplicate by document_id
            seen_ids: set = set()
            unique_records: List[Dict[str, Any]] = []
            for record in all_records:
                doc_id = record.get("document_id")
                if doc_id and doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    unique_records.append(record)

            if max_records:
                unique_records = unique_records[:max_records]

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

    def _fetch_medicines_json(self, *, days_back: int = 90) -> List[Dict[str, Any]]:
        """Fetch and parse the EMA medicines JSON data file."""
        records: List[Dict[str, Any]] = []
        since_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        try:
            logger.info("Downloading EMA medicines JSON from %s", EMA_MEDICINES_JSON)
            resp = self.session.get(EMA_MEDICINES_JSON, timeout=120)
            resp.raise_for_status()
            data = resp.json()

            items = data.get("data", data) if isinstance(data, dict) else data
            if not isinstance(items, list):
                logger.warning("EMA medicines JSON: unexpected format")
                return []

            for item in items:
                record = self._normalise_medicine(item)
                if not record:
                    continue

                # Filter by date if available
                decision_date = record.get("decision_date")
                if decision_date:
                    try:
                        dt = datetime.strptime(decision_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        if dt < since_date:
                            continue
                    except ValueError:
                        pass

                records.append(record)

        except Exception as e:
            logger.warning("EMA medicines JSON download failed: %s", e)

        logger.info("Fetched %d medicine records from EMA JSON", len(records))
        return records

    def _fetch_safety_json(self, *, days_back: int = 90) -> List[Dict[str, Any]]:
        """Fetch and parse the EMA safety (DHPC) JSON data file."""
        records: List[Dict[str, Any]] = []
        since_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        try:
            logger.info("Downloading EMA safety JSON from %s", EMA_SAFETY_JSON)
            resp = self.session.get(EMA_SAFETY_JSON, timeout=120)
            resp.raise_for_status()
            data = resp.json()

            items = data.get("data", data) if isinstance(data, dict) else data
            if not isinstance(items, list):
                logger.warning("EMA safety JSON: unexpected format")
                return []

            for item in items:
                record = self._normalise_safety(item)
                if not record:
                    continue

                decision_date = record.get("decision_date")
                if decision_date:
                    try:
                        dt = datetime.strptime(decision_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                        if dt < since_date:
                            continue
                    except ValueError:
                        pass

                records.append(record)

        except Exception as e:
            logger.warning("EMA safety JSON download failed: %s", e)

        logger.info("Fetched %d safety records from EMA JSON", len(records))
        return records

    @staticmethod
    def _normalise_medicine(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize an EMA medicines JSON record."""
        product_name = (
            item.get("name_of_medicine")
            or item.get("medicine_name")
            or item.get("product_name")
        )
        if not product_name:
            return None

        # Use medicine name + active substance as document_id
        active_substance = (
            item.get("active_substance")
            or item.get("inn")
            or item.get("active_ingredients")
        )
        document_id = f"ema-{hashlib.md5((product_name + str(active_substance)).encode()).hexdigest()[:12]}"

        # Parse the most relevant date
        decision_date = (
            item.get("european_commission_decision_date")
            or item.get("marketing_authorisation_date")
            or item.get("revision_date")
            or item.get("date_of_opinion")
        )
        if decision_date:
            decision_date = str(decision_date)[:10]

        # Determine decision type from medicine_status or category
        raw_status = str(
            item.get("medicine_status")
            or item.get("authorisation_status")
            or item.get("category")
            or ""
        ).lower().replace(" ", "_").replace("-", "_")

        decision_type = None
        if "authorised" in raw_status or "authorized" in raw_status:
            decision_type = "authorisation"
        elif "withdrawn" in raw_status:
            decision_type = "withdrawal"
        elif "suspended" in raw_status:
            decision_type = "suspension"
        elif "refused" in raw_status:
            decision_type = "withdrawal"

        return {
            "document_id": document_id,
            "document_type": "epar",
            "product_name": product_name,
            "active_substance": active_substance,
            "therapeutic_area": (
                item.get("therapeutic_area_mesh")
                or item.get("therapeutic_area")
                or item.get("atc_code_human")
            ),
            "decision_date": decision_date,
            "decision_type": decision_type,
            "document_url": item.get("url") or item.get("ema_url"),
            "summary": item.get("condition_indication"),
        }

    @staticmethod
    def _normalise_safety(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize an EMA safety/DHPC JSON record."""
        product_name = (
            item.get("name_of_medicine")
            or item.get("medicine_name")
            or item.get("product_name")
        )
        if not product_name:
            return None

        document_id = f"ema-dhpc-{hashlib.md5(product_name.encode()).hexdigest()[:12]}"

        decision_date = (
            item.get("date_of_letter")
            or item.get("date")
        )
        if decision_date:
            decision_date = str(decision_date)[:10]

        return {
            "document_id": document_id,
            "document_type": "safety_signal",
            "product_name": product_name,
            "active_substance": item.get("active_substance"),
            "therapeutic_area": item.get("therapeutic_area"),
            "decision_date": decision_date,
            "decision_type": None,
            "document_url": item.get("url"),
            "summary": item.get("description") or item.get("title"),
        }

    @staticmethod
    def _compute_hash(records: List[Dict[str, Any]]) -> str:
        """Compute a deterministic SHA-256 hash over the fetched records."""
        import json

        payload = json.dumps(records, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
