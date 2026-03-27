"""WHO ICD-11 / ICD-10 Classification API Fetcher.

Feature: 015-assessment-dashboard-integration

Fetches disease classification codes from the WHO ICD-11 Coding Tool API.
The WHO ICD-11 API is publicly accessible with OAuth2 client credentials
(client_id / client_secret from the WHO IRIS Developer Portal).

WHO ICD-11 linearization browse endpoint:
  https://id.who.int/icd/release/11/2024-01/mms/

Credentials (Doppler secrets):
  WHO_ICD_CLIENT_ID, WHO_ICD_CLIENT_SECRET

Fallback: if credentials are absent the fetcher fetches from the
ICD-10 WHO Web Services API (no auth required) for a predefined set
of common pharma-relevant chapter codes.

Stores raw API responses in raw.who_icd (JSONB envelope, migration 075).
"""

import hashlib
import json
import logging
import os
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# WHO ICD-11 OAuth2 token endpoint
ICD11_TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
# WHO ICD-11 linearization (MMS) base URL
ICD11_BASE_URL = "https://id.who.int/icd/release/11/2024-01/mms"
# WHO ICD-10 Web Services API (no auth required)
ICD10_BASE_URL = "https://apps.who.int/classifications/icd10/browse/2016/en#"

# Default ICD-10 chapter codes to fetch when using the no-auth fallback.
# These map to common pharmaceutical/clinical categories.
ICD10_DEFAULT_CHAPTERS = [
    "C00-D48",  # Neoplasms
    "D50-D89",  # Diseases of blood/immune
    "E00-E90",  # Endocrine/metabolic
    "G00-G99",  # Nervous system
    "H00-H59",  # Eye
    "I00-I99",  # Circulatory system
    "J00-J99",  # Respiratory
    "K00-K93",  # Digestive
    "L00-L99",  # Skin
    "M00-M99",  # Musculoskeletal
    "N00-N99",  # Genitourinary
]

# ICD-11 top-level chapter entity IDs (stable URIs in the MMS linearization)
ICD11_TOP_CHAPTERS = [
    "448895267",   # 1 — Certain infectious or parasitic diseases
    "1630407678",  # 2 — Neoplasms
    "1766440644",  # 3 — Diseases of the blood
    "1954798891",  # 5 — Endocrine, nutritional or metabolic diseases
    "21500692",    # 6 — Mental, behavioural or neurodevelopmental disorders
    "8417604",     # 8 — Diseases of the nervous system
    "1208484807",  # 11 — Diseases of the circulatory system
    "1303997569",  # 12 — Diseases of the respiratory system
    "1778699876",  # 13 — Diseases of the digestive system
    "576828549",   # 15 — Diseases of the musculoskeletal system
    "608594838",   # 16 — Diseases of the genitourinary system
]

MAX_RECORDS_PER_RUN = 5000


class WHOICDFetcher(BaseFetcher):
    """Fetcher for WHO ICD-11 (with ICD-10 fallback) disease codes."""

    SOURCE_NAME = "who_icd"
    BASE_URL = ICD11_BASE_URL

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)
        self._access_token: Optional[str] = None
        self.session.headers.update({
            "Accept": "application/json",
            "API-Version": "v2",
            "Accept-Language": "en",
        })

    def get_latest_url(self) -> str:
        return f"{ICD11_BASE_URL}/codeInfo/1A00"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch ICD codes from the WHO ICD-11 (or ICD-10 fallback) API.

        Keyword Args:
            max_records: Maximum records to fetch per run (default: 5000).
            use_icd10_fallback: Force ICD-10 fallback even if credentials exist.

        Returns:
            Dict with status, records (list of API response dicts), hash.
        """
        max_records = kwargs.get("max_records", MAX_RECORDS_PER_RUN)
        force_fallback = kwargs.get("use_icd10_fallback", False)

        try:
            client_id = os.environ.get("WHO_ICD_CLIENT_ID", "")
            client_secret = os.environ.get("WHO_ICD_CLIENT_SECRET", "")

            has_credentials = bool(client_id and client_secret)

            if has_credentials and not force_fallback:
                records = self._fetch_icd11(
                    client_id, client_secret, max_records=max_records
                )
                api_version = "icd11"
            else:
                if not has_credentials:
                    logger.info(
                        "WHO ICD credentials not set; falling back to ICD-10 public API"
                    )
                records = self._fetch_icd10(max_records=max_records)
                api_version = "icd10"

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
    # ICD-11 MMS linearization
    # ------------------------------------------------------------------

    def _get_icd11_token(self, client_id: str, client_secret: str) -> str:
        """Obtain OAuth2 bearer token for the WHO ICD-11 API."""
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
        token_data = response.json()
        self._access_token = token_data["access_token"]
        logger.info("Obtained WHO ICD-11 API token")
        return self._access_token

    def _fetch_icd11(
        self, client_id: str, client_secret: str, max_records: int
    ) -> List[Dict[str, Any]]:
        """Walk the ICD-11 MMS linearization chapter by chapter."""
        token = self._get_icd11_token(client_id, client_secret)
        self.session.headers.update({"Authorization": f"Bearer {token}"})

        records: List[Dict[str, Any]] = []
        seen: set = set()

        for chapter_id in ICD11_TOP_CHAPTERS:
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

    def _walk_icd11_node(
        self, entity_id: str, seen: set, remaining: int
    ) -> List[Dict[str, Any]]:
        """Recursively walk an ICD-11 MMS node, collecting leaf-level codes."""
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

        # Add a 'code' field extracted from the response for consistency
        if "code" not in data and "@id" in data:
            # Try codeInfo endpoint to get the stem code
            try:
                code_url = f"{ICD11_BASE_URL}/codeInfo/{entity_id}"
                code_resp = self.session.get(code_url, timeout=20)
                if code_resp.ok:
                    code_data = code_resp.json()
                    data["code"] = code_data.get("stemCode") or code_data.get("code")
            except Exception:
                pass

        records: List[Dict[str, Any]] = []

        # Only include nodes that have a stem code
        if data.get("code"):
            records.append(data)
            remaining -= 1

        # Recurse into children
        for child_uri in data.get("child", []):
            if remaining <= 0:
                break
            # child URIs are full URLs like https://id.who.int/icd/release/11/2024-01/mms/12345
            child_id = child_uri.rstrip("/").split("/")[-1]
            child_records = self._walk_icd11_node(child_id, seen, remaining)
            records.extend(child_records)
            remaining -= len(child_records)

        return records

    # ------------------------------------------------------------------
    # ICD-10 fallback (public API, no auth)
    # ------------------------------------------------------------------

    def _fetch_icd10(self, max_records: int) -> List[Dict[str, Any]]:
        """Fetch ICD-10 codes via the WHO ICD-10 Web Services API."""
        records: List[Dict[str, Any]] = []

        base = "https://apps.who.int/classifications/icd10/browse/2019/en/JsonGetDescendants"

        for chapter_code in ICD10_DEFAULT_CHAPTERS:
            if len(records) >= max_records:
                break
            try:
                # The ICD-10 browse API returns descendants for a block code
                url = f"{base}?iCod={chapter_code.split('-')[0]}&ConceptId={chapter_code}"
                response = self.session.get(url, timeout=30)
                if not response.ok:
                    logger.warning(
                        "ICD-10 chapter %s returned %d", chapter_code, response.status_code
                    )
                    continue

                items = response.json()
                if not isinstance(items, list):
                    items = [items]

                for item in items:
                    if len(records) >= max_records:
                        break
                    # Normalize: ensure 'code' field exists
                    if isinstance(item, dict) and item.get("code"):
                        records.append(item)

            except Exception as e:
                logger.warning("Failed to fetch ICD-10 chapter %s: %s", chapter_code, e)

        return records
