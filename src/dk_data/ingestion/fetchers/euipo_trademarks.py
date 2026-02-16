"""EUIPO Trademark Data Fetcher.

Feature: 014-uspto-euipo-model-datasource
Task: T014 — EUIPO trademark data via TMview or IBM Gateway

Fetches pharmaceutical trademark data from the European Union Intellectual
Property Office via TMview federated search API or IBM API Gateway.

Source (TMview): https://www.tmdn.org/tmview/api/search
Source (IBM): https://api.euipo.europa.eu/trademark-search
Auth: TMview (registration-based), IBM (OAuth2 + IBM Client ID)
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Rate limit: 30 req/min
REQUEST_DELAY = 2.0  # seconds between requests

# Default page size for TMview
PAGE_SIZE = 100


class EUIPOTrademarksFetcher(BaseFetcher):
    """Fetcher for EUIPO trademark data via TMview or IBM Gateway."""

    SOURCE_NAME = "euipo_trademarks"
    BASE_URL = "https://www.tmdn.org/tmview/api/search"

    # IBM Gateway endpoints
    IBM_GATEWAY_URL = "https://api.euipo.europa.eu/trademark-search"
    IBM_TOKEN_URL = "https://euipo.europa.eu/cas-server-webapp/oidc/accessToken"

    def __init__(
        self,
        data_dir: Optional[str] = None,
        backend: Optional[str] = None,
    ):
        """Initialize with selectable backend.

        Args:
            data_dir: Directory to store downloaded files.
            backend: 'tmview' or 'ibm_gateway'. Defaults to env EUIPO_BACKEND
                    or 'tmview' if not set.
        """
        super().__init__(data_dir)

        self.backend = backend or os.environ.get("EUIPO_BACKEND", "tmview")
        self.api_key: Optional[str] = os.environ.get("EUIPO_API_KEY")
        self.secret_key: Optional[str] = os.environ.get("EUIPO_SECRET_KEY")
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

        if self.backend == "ibm_gateway" and not (self.api_key and self.secret_key):
            logger.warning(
                "EUIPO_API_KEY or EUIPO_SECRET_KEY not set; "
                "IBM Gateway calls will fail. Falling back to tmview."
            )
            self.backend = "tmview"

    def get_latest_url(self) -> str:
        """Return the active backend URL."""
        if self.backend == "ibm_gateway":
            return self.IBM_GATEWAY_URL
        return self.BASE_URL

    def fetch(
        self,
        nice_classes: Optional[List[str]] = None,
        days_back: int = 7,
        max_records: int = 10000,
        **kwargs,
    ) -> Dict[str, Any]:
        """Fetch EUIPO trademark data.

        Args:
            nice_classes: Nice class codes to filter (default: ["05"]).
            days_back: Number of days to look back for filing dates.
            max_records: Maximum records to return (pagination limit).

        Returns:
            Dict with status, records, record_count, hash.
        """
        if nice_classes is None:
            nice_classes = ["05"]

        date_from = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

        try:
            logger.info(
                "Fetching EUIPO trademarks (backend=%s, classes=%s, days_back=%d, max=%d)",
                self.backend, nice_classes, days_back, max_records,
            )

            if self.backend == "ibm_gateway":
                raw_records = self._fetch_ibm_gateway(nice_classes, date_from, max_records)
            else:
                raw_records = self._fetch_tmview(nice_classes, date_from, max_records)

            # Normalize and deduplicate
            all_records: List[Dict[str, Any]] = []
            seen_ids: set = set()

            for raw in raw_records:
                normalized = self._normalize_trademark(raw)
                if normalized:
                    app_num = normalized.get("application_number")
                    if app_num and app_num not in seen_ids:
                        seen_ids.add(app_num)
                        all_records.append(normalized)

            content_hash = hashlib.md5(
                str(sorted(seen_ids)).encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": all_records,
                "record_count": len(all_records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(all_records)})
            return result

        except Exception as e:
            logger.exception("Failed to fetch EUIPO trademark data: %s", e)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_tmview(
        self,
        nice_classes: List[str],
        date_from: str,
        max_records: int,
    ) -> List[Dict[str, Any]]:
        """Fetch from TMview API.

        POST https://www.tmdn.org/tmview/api/search
        Body: {pageSize, pageIndex, criteria: {niceClasses, tradeMarkOffices, ...}}
        """
        records: List[Dict[str, Any]] = []
        page_index = 0

        while len(records) < max_records:
            body = {
                "pageSize": min(PAGE_SIZE, max_records - len(records)),
                "pageIndex": page_index,
                "criteria": {
                    "niceClasses": nice_classes,
                    "tradeMarkOffices": ["EM"],
                    "applicationDateFrom": date_from,
                },
            }

            try:
                response = self.session.post(
                    self.BASE_URL,
                    json=body,
                    timeout=60,
                )

                if response.status_code >= 500:
                    logger.warning("TMview returned %d, stopping pagination", response.status_code)
                    break

                response.raise_for_status()
                data = response.json()

                items = data.get("tradeMarks") or data.get("results") or []
                if not items:
                    break

                records.extend(items)

                if len(items) < PAGE_SIZE:
                    break

                page_index += 1
                time.sleep(REQUEST_DELAY)

            except Exception as e:
                logger.warning("TMview request failed at page %d: %s", page_index, e)
                break

        return records

    def _fetch_ibm_gateway(
        self,
        nice_classes: List[str],
        date_from: str,
        max_records: int,
    ) -> List[Dict[str, Any]]:
        """Fetch from IBM API Gateway.

        Uses OAuth2 token from EUIPO CAS server.
        Adds X-IBM-Client-Id header.
        """
        records: List[Dict[str, Any]] = []

        # Authenticate
        self._ensure_ibm_token()

        page_index = 0
        while len(records) < max_records:
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "X-IBM-Client-Id": self.api_key,
            }

            params = {
                "niceClasses": ",".join(nice_classes),
                "offices": "EM",
                "applicationDateFrom": date_from,
                "pageSize": min(PAGE_SIZE, max_records - len(records)),
                "pageIndex": page_index,
            }

            try:
                response = self.session.get(
                    self.IBM_GATEWAY_URL,
                    params=params,
                    headers=headers,
                    timeout=60,
                )

                if response.status_code >= 500:
                    logger.warning("IBM Gateway returned %d, stopping", response.status_code)
                    break

                response.raise_for_status()
                data = response.json()

                items = data.get("tradeMarks") or data.get("results") or []
                if not items:
                    break

                records.extend(items)

                if len(items) < PAGE_SIZE:
                    break

                page_index += 1
                time.sleep(REQUEST_DELAY)

            except Exception as e:
                logger.warning("IBM Gateway request failed at page %d: %s", page_index, e)
                break

        return records

    def _ensure_ibm_token(self) -> None:
        """Obtain or refresh OAuth2 access token for IBM Gateway."""
        if self._access_token and time.time() < self._token_expires_at:
            return

        if not self.api_key or not self.secret_key:
            raise RuntimeError("EUIPO_API_KEY and EUIPO_SECRET_KEY are required for IBM Gateway")

        logger.debug("Requesting EUIPO IBM Gateway access token")
        response = self.session.post(
            self.IBM_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.api_key,
                "client_secret": self.secret_key,
            },
            headers={"Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        token_data = response.json()

        self._access_token = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", 3600))
        self._token_expires_at = time.time() + expires_in - 60

        logger.info("EUIPO IBM Gateway token obtained (expires_in=%d)", expires_in)

    @staticmethod
    def _normalize_trademark(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize TMview/IBM response to flat record.

        Maps response fields to raw table columns:
        - applicationNumber -> application_number
        - tradeMarkName -> mark_name
        - tradeMarkType -> mark_kind
        - status -> status
        - applicationDate -> filing_date
        - registrationDate -> registration_date
        - expiryDate -> expiry_date
        - niceClasses -> nice_classes
        - applicantName -> applicant_name
        """
        application_number = (
            raw.get("applicationNumber")
            or raw.get("application_number")
            or raw.get("ST13")
        )
        if not application_number:
            return None

        # Extract Nice classes
        nice_classes_raw = raw.get("niceClasses") or raw.get("nice_classes") or []
        nice_classes: List[int] = []
        if isinstance(nice_classes_raw, list):
            for c in nice_classes_raw:
                if isinstance(c, int):
                    nice_classes.append(c)
                elif isinstance(c, str) and c.isdigit():
                    nice_classes.append(int(c))

        return {
            "application_number": str(application_number),
            "mark_name": raw.get("tradeMarkName") or raw.get("mark_name"),
            "mark_kind": raw.get("tradeMarkType") or raw.get("mark_kind"),
            "mark_feature": raw.get("markFeature") or raw.get("mark_feature"),
            "mark_basis": raw.get("markBasis") or raw.get("mark_basis"),
            "applicant_name": raw.get("applicantName") or raw.get("applicant_name"),
            "applicant_country": raw.get("applicantCountry") or raw.get("applicant_country"),
            "representative_name": raw.get("representativeName") or raw.get("representative_name"),
            "status": raw.get("status") or raw.get("markStatus"),
            "filing_date": raw.get("applicationDate") or raw.get("filing_date"),
            "registration_date": raw.get("registrationDate") or raw.get("registration_date"),
            "expiry_date": raw.get("expiryDate") or raw.get("expiry_date"),
            "nice_classes": sorted(set(nice_classes)) if nice_classes else None,
            "goods_and_services": raw.get("goodsAndServices") or raw.get("goods_and_services"),
            "image_url": raw.get("imageUrl") or raw.get("image_url"),
        }
