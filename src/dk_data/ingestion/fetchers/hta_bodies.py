"""HTA Bodies Decision Fetcher.

Feature: 011-datasource-integration
Task: T058-T060 — HTA Bodies CI source integration

Fetches technology appraisal decisions from Health Technology Assessment
(HTA) bodies.  Currently implements NICE (UK) as the primary agency;
G-BA (Germany), HAS (France), and PBAC (Australia) are provided as
stubs that return empty results pending API/scraping implementation.

Query-scoped from meta.ci_search_terms WHERE term_type = 'drug_name'.
Weekly cadence.

Sources:
- NICE: https://www.nice.org.uk/guidance/published?type=ta
- G-BA: https://www.g-ba.de/bewertungsverfahren/nutzenbewertung/
- HAS: https://www.has-sante.fr/
- PBAC: https://www.pbs.gov.au/pbs/industry/listing/elements/pbac-meetings
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# NICE API base for technology appraisals
NICE_API_BASE = "https://www.nice.org.uk/api/guidance/published"

# NICE API key — required for org-authenticated access.
# Register at https://www.nice.org.uk/corporate/ecd10 (requires org eligibility).
# Set env var NICE_API_KEY; without it the request will likely return 401/403.
_NICE_API_KEY = os.environ.get("NICE_API_KEY", "")

# Agency identifiers
AGENCIES = ["nice", "gba", "has", "pbac"]


class HTABodiesFetcher(BaseFetcher):
    """Fetcher for HTA body decisions (multi-agency CI scope)."""

    SOURCE_NAME = "hta_bodies"
    BASE_URL = "https://www.nice.org.uk"

    def get_latest_url(self) -> str:
        """Return the NICE guidance API URL."""
        return NICE_API_BASE

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch HTA decisions from all configured agencies.

        Keyword Args:
            days_back: Number of days to look back (default: 7).
            drug_names: Optional list of drug name strings to search.
                        If not provided, reads from DB.
            agencies: Optional list of agency codes (default: all).

        Returns:
            Dict with keys: status, records, hash, error (on failure).
        """
        days_back = kwargs.get("days_back", 7)
        agencies = kwargs.get("agencies", AGENCIES)

        try:
            drug_names = kwargs.get("drug_names") or self._get_drug_names()

            logger.info(
                "Fetching HTA decisions (days_back=%d, agencies=%s, drugs=%d)",
                days_back, agencies, len(drug_names),
            )

            all_records: List[Dict[str, Any]] = []
            seen_ids: set = set()

            for agency in agencies:
                try:
                    records = self._fetch_agency(
                        agency,
                        drug_names=drug_names,
                        days_back=days_back,
                    )
                    for record in records:
                        decision_id = record.get("decision_id")
                        if decision_id and decision_id not in seen_ids:
                            seen_ids.add(decision_id)
                            all_records.append(record)
                except Exception as e:
                    logger.warning(
                        "Failed to fetch from %s: %s", agency, e
                    )
                    continue

            # Compute content hash
            content_hash = hashlib.md5(
                ",".join(sorted(seen_ids)).encode()
            ).hexdigest() if seen_ids else None

            result: Dict[str, Any] = {
                "status": "success",
                "records": all_records,
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(all_records)})
            return result

        except Exception as e:
            logger.exception("HTA bodies fetch failed: %s", e)
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

    def _get_drug_names(self) -> List[str]:
        """Read drug names from meta.ci_search_terms.

        Returns:
            List of drug name strings.
        """
        try:
            from ..utils.database import get_connection

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT term_value
                        FROM meta.ci_search_terms
                        WHERE term_type = 'drug_name'
                          AND is_active = TRUE
                        ORDER BY term_id
                        """
                    )
                    rows = cur.fetchall()

            names = [row[0] for row in rows]
            if names:
                logger.info(
                    "Loaded %d drug names from meta.ci_search_terms",
                    len(names),
                )
            return names

        except Exception as e:
            logger.warning(
                "Could not read drug names from DB: %s", e
            )
            return []

    def _fetch_agency(
        self,
        agency: str,
        *,
        drug_names: List[str],
        days_back: int = 7,
    ) -> List[Dict[str, Any]]:
        """Dispatch fetch to the appropriate agency handler.

        Args:
            agency: Agency code (nice, gba, has, pbac).
            drug_names: Drug names to search for.
            days_back: Look-back window in days.

        Returns:
            List of normalized decision record dicts.
        """
        dispatch = {
            "nice": self._fetch_nice,
            "gba": self._fetch_gba_stub,
            "has": self._fetch_has_stub,
            "pbac": self._fetch_pbac_stub,
        }
        handler = dispatch.get(agency)
        if handler is None:
            logger.warning("Unknown HTA agency: %s", agency)
            return []
        return handler(drug_names=drug_names, days_back=days_back)

    # ------------------------------------------------------------------
    # NICE (UK) — primary implementation
    # ------------------------------------------------------------------

    def _fetch_nice(
        self,
        *,
        drug_names: List[str],
        days_back: int = 7,
    ) -> List[Dict[str, Any]]:
        """Fetch NICE technology appraisal decisions.

        Queries the NICE published guidance API for technology appraisals
        updated within the look-back window.

        Args:
            drug_names: Drug names to filter (post-fetch text match).
            days_back: Look-back window in days.

        Returns:
            List of normalized HTA decision dicts.
        """
        since_date = (
            datetime.now(timezone.utc) - timedelta(days=days_back)
        ).strftime("%Y-%m-%d")

        params = {
            "type": "ta",  # Technology Appraisals
            "from": since_date,
        }

        # NICE API requires org-gated API key (Ocp-Apim-Subscription-Key header).
        # Without it, the request returns 401/403. Return empty gracefully if not configured.
        if not _NICE_API_KEY:
            logger.warning(
                "NICE_API_KEY not set — NICE API requires organizational API key. "
                "Register at https://www.nice.org.uk/corporate/ecd10. Returning empty."
            )
            return []

        headers = {"API-Key": _NICE_API_KEY}
        try:
            response = self.session.get(NICE_API_BASE, params=params, headers=headers, timeout=30)
            if response.status_code in (401, 403):
                logger.warning(
                    "NICE API returned %d — API key may be invalid or not yet approved. "
                    "Check NICE_API_KEY env var.",
                    response.status_code,
                )
                return []
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning("NICE API request failed: %s", e)
            return []

        items = self._extract_items(data)
        if not items:
            logger.info("No NICE guidance items returned")
            return []

        records: List[Dict[str, Any]] = []
        drug_names_lower = [d.lower() for d in drug_names] if drug_names else []

        for item in items:
            record = self._normalize_nice_item(item)
            if not record:
                continue

            # If drug_names are specified, filter by name match
            if drug_names_lower:
                item_drug = (record.get("drug_name") or "").lower()
                item_title = (record.get("summary") or "").lower()
                if not any(
                    dn in item_drug or dn in item_title
                    for dn in drug_names_lower
                ):
                    continue

            records.append(record)

        logger.info("Fetched %d NICE TA decisions", len(records))
        return records

    @staticmethod
    def _extract_items(data: Any) -> List[Dict]:
        """Extract list of items from a NICE API response."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("results", "data", "items", "guidance"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []

    @staticmethod
    def _normalize_nice_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize a NICE guidance item to the raw.hta_decisions schema.

        Returns None if no usable decision ID can be extracted.
        """
        decision_id = (
            item.get("id")
            or item.get("guidance_id")
            or item.get("reference")
        )
        if not decision_id:
            return None

        decision_id = f"nice-{decision_id}"

        # Decision date
        decision_date = (
            item.get("decision_date")
            or item.get("last_modified")
            or item.get("published_date")
            or item.get("date")
        )
        if decision_date:
            decision_date = str(decision_date)[:10]

        return {
            "decision_id": decision_id,
            "agency": "nice",
            "drug_name": item.get("drug_name") or item.get("title"),
            "indication": item.get("indication") or item.get("therapeutic_area"),
            "decision_type": item.get("decision_type") or item.get("type"),
            "decision_date": decision_date,
            "document_url": item.get("url") or item.get("document_url"),
            "summary": item.get("summary") or item.get("description"),
        }

    # ------------------------------------------------------------------
    # Stub implementations for other agencies
    # ------------------------------------------------------------------

    def _fetch_gba_stub(
        self, *, drug_names: List[str], days_back: int = 7
    ) -> List[Dict[str, Any]]:
        """G-BA (Germany) — stub, returns empty results.

        TODO: Implement G-BA Nutzenbewertung scraping.
        """
        logger.info("G-BA fetcher is a stub; returning empty results")
        return []

    def _fetch_has_stub(
        self, *, drug_names: List[str], days_back: int = 7
    ) -> List[Dict[str, Any]]:
        """HAS (France) — stub, returns empty results.

        TODO: Implement HAS transparency committee opinion scraping.
        """
        logger.info("HAS fetcher is a stub; returning empty results")
        return []

    def _fetch_pbac_stub(
        self, *, drug_names: List[str], days_back: int = 7
    ) -> List[Dict[str, Any]]:
        """PBAC (Australia) — stub, returns empty results.

        TODO: Implement PBAC meeting outcomes scraping.
        """
        logger.info("PBAC fetcher is a stub; returning empty results")
        return []
