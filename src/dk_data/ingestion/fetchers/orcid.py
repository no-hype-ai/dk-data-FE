"""ORCID Public API Data Fetcher.

Feature: 012-platform-hardening (US3)

Fetches researcher profiles from the ORCID public API.
Authenticates via OAuth2 client credentials grant for reliable access
(12 req/s authenticated vs unauthenticated which may be blocked).

Register at: https://orcid.org → Developer Tools
Set ORCID_CLIENT_ID and ORCID_CLIENT_SECRET in Doppler.

Source: https://pub.orcid.org/v3.0/
Docs: https://info.orcid.org/documentation/api-tutorials/api-tutorial-searching-the-orcid-registry/
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests as req_lib

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class ORCIDFetcher(BaseFetcher):
    """Fetcher for ORCID researcher profiles via public API with OAuth2."""

    SOURCE_NAME = "orcid"
    BASE_URL = "https://pub.orcid.org/v3.0"
    TOKEN_URL = "https://orcid.org/oauth/token"

    MAX_RESULTS = 1000

    # ORCID API page size cap
    PAGE_SIZE = 200

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)
        self.session.headers.update({"Accept": "application/json"})

        self._client_id = os.environ.get("ORCID_CLIENT_ID")
        self._client_secret = os.environ.get("ORCID_CLIENT_SECRET")
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

        if self._client_id and self._client_secret:
            logger.info("ORCID OAuth2 credentials detected; will use authenticated access")
            self._authenticate()
        else:
            logger.warning(
                "No ORCID_CLIENT_ID/ORCID_CLIENT_SECRET set. "
                "Register at https://orcid.org → Developer Tools"
            )

    def _authenticate(self) -> None:
        """Obtain OAuth2 access token via client credentials grant."""
        try:
            response = req_lib.post(
                self.TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "client_credentials",
                    "scope": "/read-public",
                },
                headers={"Accept": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            self._access_token = data["access_token"]
            expires_in = data.get("expires_in", 631138518)  # ORCID tokens are long-lived
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)

            self.session.headers["Authorization"] = f"Bearer {self._access_token}"
            logger.info("ORCID OAuth2 token obtained successfully")
        except Exception as e:
            logger.error(f"Failed to obtain ORCID OAuth2 token: {e}")
            self._access_token = None

    def _ensure_token(self) -> None:
        """Refresh token if expired."""
        if self._access_token and self._token_expires_at:
            if datetime.now() < (self._token_expires_at - timedelta(seconds=60)):
                return
        if self._client_id and self._client_secret:
            self._authenticate()

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
        resume = kwargs.get("resume", True)

        manifest = self.load_manifest()
        resume_offset: int = manifest.get("last_offset", 0) if resume else 0

        try:
            orcid_ids = self._search(query, max_results=max_results,
                                     resume_offset=resume_offset)

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

            self.save_manifest(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_run_status="completed",
                total_records_fetched=len(records),
                last_content_hash=content_hash,
                last_offset=0,  # Reset — run completed cleanly
            )

            result = {"status": "success", "records": records, "hash": content_hash}
            self.log_fetch_result({**result, "records": len(records)})
            return result

        except Exception as e:
            logger.exception(f"ORCID fetch failed: {e}")
            self.save_manifest(
                last_run_status="interrupted",
                last_offset=getattr(self, "_last_offset", 0),
            )
            result = {"status": "failed", "records": [], "hash": None, "error": str(e)}
            self.log_fetch_result(result)
            return result

    def _search(
        self,
        query: str,
        max_results: int = 1000,
        resume_offset: int = 0,
    ) -> List[str]:
        """Search ORCID and return ORCID iDs with offset pagination."""
        self._ensure_token()
        url = f"{self.BASE_URL}/search"
        all_ids: List[str] = []
        start = resume_offset

        while len(all_ids) < max_results:
            rows = min(self.PAGE_SIZE, max_results - len(all_ids))
            params = {"q": query, "start": str(start), "rows": str(rows)}

            data = self.fetch_json(url, params=params)
            results = data.get("result", [])
            if not results:
                break

            batch_ids = [
                r["orcid-identifier"]["path"]
                for r in results
                if r.get("orcid-identifier")
            ]
            all_ids.extend(batch_ids)

            total = data.get("num-found", 0)
            start += len(results)
            self._last_offset = start
            self.save_manifest(last_offset=start, last_run_status="in_progress")

            if start >= total or len(results) < rows:
                break

            time.sleep(0.09)  # ~12 req/s — stay under authenticated rate limit

        logger.info(f"[orcid] Collected {len(all_ids)} ORCID iDs")
        return all_ids[:max_results]

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

                # Rate limit: 24 req/s max with OAuth2, 12 recommended
                time.sleep(0.09)

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
