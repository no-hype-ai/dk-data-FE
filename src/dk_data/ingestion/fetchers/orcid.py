"""ORCID Public API Data Fetcher.

Feature: 012-platform-hardening (US3)

Fetches researcher profiles from the ORCID public API.
Uses the public API (no registration required).

Source: https://pub.orcid.org/v3.0/
"""

import hashlib
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class ORCIDFetcher(BaseFetcher):
    """Fetcher for ORCID researcher profiles via public API."""

    SOURCE_NAME = "orcid"
    BASE_URL = "https://pub.orcid.org/v3.0"

    MAX_RESULTS = 200

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)
        self.session.headers.update({"Accept": "application/json"})

    def get_latest_url(self) -> str:
        return f"{self.BASE_URL}/search"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch ORCID researcher profiles.

        Keyword Args:
            query: ORCID search query. Defaults to pharmaceutical researchers.
            max_results: Maximum profiles. Defaults to 200.

        Returns:
            Dict with keys: status, records, hash, error (on failure).
        """
        query = kwargs.get("query", "keyword:pharmaceutical OR keyword:drug discovery")
        max_results = kwargs.get("max_results", self.MAX_RESULTS)

        try:
            orcid_ids = self._search(query, max_results=max_results)

            if not orcid_ids:
                result = {
                    "status": "success",
                    "records": [],
                    "hash": None,
                    "message": "No ORCID profiles found",
                }
                self.log_fetch_result(result)
                return result

            logger.info(f"ORCID search returned {len(orcid_ids)} profiles")

            records = self._fetch_profiles(orcid_ids)

            content_hash = hashlib.md5(
                ",".join(sorted(orcid_ids)).encode()
            ).hexdigest()

            result = {"status": "success", "records": records, "hash": content_hash}
            self.log_fetch_result({**result, "records": len(records)})
            return result

        except Exception as e:
            logger.exception(f"ORCID fetch failed: {e}")
            result = {"status": "failed", "records": [], "hash": None, "error": str(e)}
            self.log_fetch_result(result)
            return result

    def _search(self, query: str, max_results: int = 200) -> List[str]:
        """Search ORCID and return ORCID iDs."""
        url = f"{self.BASE_URL}/search"
        params = {"q": query, "rows": str(min(max_results, 200))}

        data = self.fetch_json(url, params=params)
        results = data.get("result", [])
        return [r["orcid-identifier"]["path"] for r in results if r.get("orcid-identifier")]

    def _fetch_profiles(self, orcid_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch full profile for each ORCID iD."""
        records = []
        for orcid_id in orcid_ids:
            try:
                url = f"{self.BASE_URL}/{orcid_id}/record"
                data = self.fetch_json(url)

                person = data.get("person", {})
                name = person.get("name", {})
                bio = person.get("biography", {})
                keywords_data = person.get("keywords", {})
                employments = data.get("activities-summary", {}).get("employments", {})

                records.append({
                    "orcid_id": orcid_id,
                    "given_names": (name.get("given-names", {}).get("value") if name else None),
                    "family_name": (name.get("family-name", {}).get("value") if name else None),
                    "credit_name": (name.get("credit-name", {}).get("value") if name else None),
                    "biography": (bio.get("content") if bio else None),
                    "keywords": [
                        kw.get("content")
                        for kw in keywords_data.get("keyword", [])
                        if kw.get("content")
                    ] if keywords_data else [],
                    "current_affiliations": self._parse_employments(employments),
                    "works_count": data.get("activities-summary", {}).get("works", {}).get("group", []),
                    "external_ids": self._parse_external_ids(person),
                    "raw_response": data,
                })

                # Rate limit: public API is 24 req/s but be conservative
                time.sleep(0.1)

            except Exception as e:
                logger.warning(f"Failed to fetch ORCID profile {orcid_id}: {e}")
        return records

    def _parse_employments(self, employments: Dict) -> List[Dict[str, str]]:
        """Parse employment affiliations."""
        affiliations = []
        for group in employments.get("affiliation-group", []):
            for summary in group.get("summaries", []):
                emp = summary.get("employment-summary", {})
                org = emp.get("organization", {})
                affiliations.append({
                    "organization": org.get("name", ""),
                    "role": emp.get("role-title", ""),
                    "department": emp.get("department-name", ""),
                })
        return affiliations

    def _parse_external_ids(self, person: Dict) -> Dict[str, str]:
        """Parse external identifiers (Scopus, ResearcherID, etc.)."""
        ids = {}
        external = person.get("external-identifiers", {})
        for eid in external.get("external-identifier", []):
            id_type = eid.get("external-id-type", "unknown")
            id_value = eid.get("external-id-value", "")
            ids[id_type] = id_value
        return ids
