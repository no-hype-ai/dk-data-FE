"""WHO ICD-11 / ICD-10 Classification API Fetcher.

Feature: 015-assessment-dashboard-integration

Fetches disease classification codes from the WHO ICD-11 Coding Tool API.
Credentials (free) from the WHO ICD API developer portal:
  https://icd.who.int/icdapi

Both ICD-11 and ICD-10 require the same OAuth2 client credentials.
The old apps.who.int ICD-10 public API was decommissioned by WHO.

Chapter discovery is dynamic — the fetcher walks from the linearization
root so no entity IDs are hardcoded and releases (2024-01, 2025-01, …)
are picked up automatically.

Doppler secrets: WHO_ICD_CLIENT_ID, WHO_ICD_CLIENT_SECRET

Stores raw API responses in raw.who_icd (JSONB envelope, migration 075).
"""

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Set

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# WHO ICD-11 OAuth2 token endpoint
ICD11_TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
# WHO ICD-11 MMS linearization root — bump release tag (2024-01 → 2025-01) when WHO publishes new release
ICD11_BASE_URL = "https://id.who.int/icd/release/11/2024-01/mms"
# WHO ICD-10 linearization root (same OAuth2 auth)
ICD10_BASE_URL = "https://id.who.int/icd/release/10/2019"

MAX_RECORDS_PER_RUN = 5000

# WHO ICD-11 API enforces ~1 req/s for registered users; ICD-10 is equally sensitive.
REQUEST_DELAY = 1.1  # seconds between requests


class WHOICDFetcher(BaseFetcher):
    """Fetcher for WHO ICD-11 (with ICD-10 fallback) disease codes.

    Chapter discovery is dynamic: both _fetch_icd11 and _fetch_icd10
    start from the linearization root URL and discover chapters from the
    'child' array returned by the API. No entity IDs or chapter codes are
    hardcoded — new WHO releases are picked up automatically.
    """

    SOURCE_NAME = "who_icd"
    BASE_URL = ICD11_BASE_URL

    def __init__(self, data_dir: Optional[str] = None):
        # WHO ICD APIs are slow and rate-limited; reduce retries to avoid 3×30s storms.
        super().__init__(data_dir, max_retries=1, retry_base_delay_seconds=2.0)
        self._access_token: Optional[str] = None
        self.session.headers.update({
            "Accept": "application/json",
            "API-Version": "v2",
            "Accept-Language": "en",
        })

    def get_latest_url(self) -> str:
        return ICD11_BASE_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch ICD codes from the WHO ICD-11 (or ICD-10 fallback) API.

        Keyword Args:
            max_records: Maximum records to fetch per run (default: 5000).
            use_icd10_fallback: Force ICD-10 instead of ICD-11 (default: False).

        Returns:
            Dict with status, records (list of API response dicts), hash.
        """
        max_records = kwargs.get("max_records", MAX_RECORDS_PER_RUN)
        force_fallback = kwargs.get("use_icd10_fallback", False)

        try:
            client_id = os.environ.get("WHO_ICD_CLIENT_ID", "")
            client_secret = os.environ.get("WHO_ICD_CLIENT_SECRET", "")

            if not client_id or not client_secret:
                raise RuntimeError(
                    "WHO_ICD_CLIENT_ID and WHO_ICD_CLIENT_SECRET are required. "
                    "Register for free credentials at https://icd.who.int/icdapi"
                )

            if force_fallback:
                records = self._fetch_icd10(client_id, client_secret, max_records)
                api_version = "icd10"
            else:
                records = self._fetch_icd11(client_id, client_secret, max_records)
                api_version = "icd11"

            content_hash = hashlib.md5(
                json.dumps(
                    [r.get("code") or r.get("@id", "") for r in records],
                    sort_keys=True,
                ).encode()
            ).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
                "api_version": api_version,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as e:
            logger.exception("WHO ICD fetch failed: %s", e)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _get_token(self, client_id: str, client_secret: str) -> str:
        """Obtain and cache an OAuth2 bearer token."""
        if self._access_token:
            return self._access_token
        response = self.session.post(
            ICD11_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "icdapi_access",
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        response.raise_for_status()
        self._access_token = response.json()["access_token"]
        logger.info("Obtained WHO ICD API token")
        return self._access_token

    # ------------------------------------------------------------------
    # ICD-11 MMS linearization — dynamic chapter discovery
    # ------------------------------------------------------------------

    def _fetch_icd11(
        self, client_id: str, client_secret: str, max_records: int
    ) -> List[Dict[str, Any]]:
        """Walk the ICD-11 MMS linearization starting from the root.

        Discovers top-level chapters dynamically from the root 'child' array
        so no entity IDs need to be hardcoded.
        """
        token = self._get_token(client_id, client_secret)
        self.session.headers.update({"Authorization": f"Bearer {token}"})

        # Discover top-level chapters from the linearization root
        chapter_ids = self._discover_top_chapters(ICD11_BASE_URL)
        logger.info("ICD-11: discovered %d top-level chapters", len(chapter_ids))

        records: List[Dict[str, Any]] = []
        seen: Set[str] = set()

        for chapter_id in chapter_ids:
            if len(records) >= max_records:
                break
            try:
                chapter_records = self._walk_icd11_node(
                    chapter_id, seen, max_records - len(records)
                )
                records.extend(chapter_records)
            except Exception as e:
                logger.warning("Failed to fetch ICD-11 chapter %s: %s", chapter_id, e)

        return records

    def _discover_top_chapters(self, base_url: str) -> List[str]:
        """Fetch the linearization root and return entity IDs of all top-level chapters."""
        try:
            response = self.session.get(base_url, timeout=30)
            response.raise_for_status()
            root = response.json()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch ICD linearization root {base_url}: {e}") from e
        finally:
            time.sleep(REQUEST_DELAY)

        chapter_ids = []
        for child_uri in root.get("child", []):
            entity_id = child_uri.rstrip("/").split("/")[-1]
            chapter_ids.append(entity_id)

        if not chapter_ids:
            raise RuntimeError(
                f"ICD linearization root returned no children — "
                f"check release URL: {base_url}"
            )

        return chapter_ids

    def _walk_icd11_node(
        self, entity_id: str, seen: Set[str], remaining: int
    ) -> List[Dict[str, Any]]:
        """Recursively walk an ICD-11 MMS node, collecting coded entries."""
        if remaining <= 0 or entity_id in seen:
            return []

        seen.add(entity_id)
        url = f"{ICD11_BASE_URL}/{entity_id}"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning("Failed to fetch ICD-11 entity %s: %s", entity_id, e)
            return []
        finally:
            time.sleep(REQUEST_DELAY)

        # 'code' is returned directly for most nodes; for those that don't have it,
        # skip the codeInfo lookup — those are structural/grouping nodes without stem codes.
        records: List[Dict[str, Any]] = []
        if data.get("code"):
            records.append(data)
            remaining -= 1

        for child_uri in data.get("child", []):
            if remaining <= 0:
                break
            child_id = child_uri.rstrip("/").split("/")[-1]
            child_records = self._walk_icd11_node(child_id, seen, remaining)
            records.extend(child_records)
            remaining -= len(child_records)

        return records

    # ------------------------------------------------------------------
    # ICD-10 fallback — dynamic chapter discovery, full recursive walk (same auth)
    # ------------------------------------------------------------------

    def _fetch_icd10(
        self, client_id: str, client_secret: str, max_records: int
    ) -> List[Dict[str, Any]]:
        """Walk the entire ICD-10 linearization recursively starting from the root.

        ICD-10 has 4 hierarchy levels: chapter → block → 3-char → 4-char leaf.
        All levels are walked recursively so actual clinical codes (e.g. A00.0)
        are captured, not just structural chapter/block nodes.
        Discovers chapters dynamically — no chapter codes are hardcoded.
        """
        token = self._get_token(client_id, client_secret)
        self.session.headers.update({"Authorization": f"Bearer {token}"})

        chapter_ids = self._discover_top_chapters(ICD10_BASE_URL)
        logger.info("ICD-10: discovered %d top-level chapters", len(chapter_ids))

        records: List[Dict[str, Any]] = []
        seen: Set[str] = set()

        for chapter_id in chapter_ids:
            if len(records) >= max_records:
                break
            try:
                chapter_records = self._walk_icd10_node(
                    chapter_id, seen, max_records - len(records)
                )
                records.extend(chapter_records)
            except Exception as e:
                logger.warning("Failed to fetch ICD-10 chapter %s: %s", chapter_id, e)

        return records

    def _walk_icd10_node(
        self, node_id: str, seen: Set[str], remaining: int
    ) -> List[Dict[str, Any]]:
        """Recursively walk an ICD-10 node, collecting all coded entries.

        ICD-10 nodes always have a 'code' field at every level (chapter 'I',
        block 'A00-A09', 3-char 'A00', 4-char 'A00.0').
        title uses the same {"@language": "en", "@value": "..."} structure as ICD-11.
        Additional fields: codingHint (some nodes), inclusion, exclusion, classKind.
        """
        if remaining <= 0 or node_id in seen:
            return []

        seen.add(node_id)
        url = f"{ICD10_BASE_URL}/{node_id}"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning("Failed to fetch ICD-10 entity %s: %s", node_id, e)
            return []
        finally:
            time.sleep(REQUEST_DELAY)

        records: List[Dict[str, Any]] = []
        if data.get("code"):
            records.append(data)
            remaining -= 1

        for child_uri in data.get("child", []):
            if remaining <= 0:
                break
            child_id = child_uri.rstrip("/").split("/")[-1]
            child_records = self._walk_icd10_node(child_id, seen, remaining)
            records.extend(child_records)
            remaining -= len(child_records)

        return records
