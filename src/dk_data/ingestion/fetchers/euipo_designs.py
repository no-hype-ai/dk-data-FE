"""EUIPO Design Search Fetcher.

Feature: 014-uspto-euipo-model-datasource
Fetches registered community design (RCD) data from EUIPO IBM API Gateway.

Tracks pharmaceutical packaging, medical device housings, and other
healthcare-related industrial designs filed at the EU level.

Source: https://api.euipo.europa.eu/design-search
Auth: OAuth2 client credentials (same EUIPO_API_KEY/EUIPO_SECRET_KEY as trademarks)
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

REQUEST_DELAY = 2.0  # seconds between requests (30 req/min limit)
PAGE_SIZE = 100


class EUIPODesignsFetcher(BaseFetcher):
    """Fetcher for EUIPO registered community design data via IBM Gateway."""

    SOURCE_NAME = "euipo_designs"
    BASE_URL = "https://api.euipo.europa.eu/design-search/designs"

    TOKEN_URL = "https://auth.euipo.europa.eu/oidc/accessToken"

    # Locarno classes relevant to pharma/healthcare/medical devices
    # 24: Medical and laboratory equipment
    # 09: Packages and containers (drug packaging)
    # 24-01: Surgical and medical instruments
    # 24-02: Medical apparatus, instruments and equipment
    DEFAULT_LOCARNO_CLASSES = ["24", "09"]

    def __init__(self, data_dir: Optional[str] = None):
        super().__init__(data_dir)
        self.api_key: Optional[str] = os.environ.get("EUIPO_API_KEY")
        self.secret_key: Optional[str] = os.environ.get("EUIPO_SECRET_KEY")
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

    def get_latest_url(self) -> str:
        return self.BASE_URL

    def fetch(
        self,
        locarno_classes: Optional[List[str]] = None,
        days_back: int = 30,
        max_records: int = 10000,
        **kwargs,
    ) -> Dict[str, Any]:
        """Fetch EUIPO design registrations.

        Args:
            locarno_classes: Locarno classification codes to filter.
                Default: ["24", "09"] (medical equipment + packaging).
            days_back: Number of days to look back for filing dates.
            max_records: Maximum records to return.

        Returns:
            Dict with status, records, record_count, hash.
        """
        if locarno_classes is None:
            locarno_classes = self.DEFAULT_LOCARNO_CLASSES

        date_from = (
            datetime.now(timezone.utc) - timedelta(days=days_back)
        ).strftime("%Y-%m-%d")

        try:
            logger.info(
                "Fetching EUIPO designs (classes=%s, days_back=%d, max=%d)",
                locarno_classes, days_back, max_records,
            )

            if not self.api_key or not self.secret_key:
                msg = (
                    "EUIPO_API_KEY/EUIPO_SECRET_KEY not set. "
                    "Obtain from https://developers.euipo.europa.eu and set in Doppler."
                )
                logger.warning(msg)
                result = {
                    "status": "source_unavailable",
                    "records": [],
                    "record_count": 0,
                    "hash": None,
                    "error": msg,
                }
                self.log_fetch_result(result)
                return result

            try:
                self._ensure_token()
            except Exception as auth_err:
                err_str = str(auth_err)
                # 5xx on auth endpoint = EUIPO infrastructure outage
                if any(code in err_str for code in ("502", "503", "504", "500")):
                    msg = f"EUIPO auth server unavailable (5xx): {auth_err}"
                    logger.warning(msg)
                    result = {
                        "status": "source_unavailable",
                        "records": [],
                        "record_count": 0,
                        "hash": None,
                        "error": msg,
                    }
                    self.log_fetch_result(result)
                    return result
                raise

            records: List[Dict[str, Any]] = []
            api_errors = 0
            page = 0

            while len(records) < max_records:
                headers = {
                    "Authorization": f"Bearer {self._access_token}",
                    "X-IBM-Client-Id": self.api_key,
                }
                params = {
                    "locarnoClasses": ",".join(locarno_classes),
                    "offices": "EM",
                    "applicationDateFrom": date_from,
                    "size": min(PAGE_SIZE, max_records - len(records)),
                    "page": page,
                }

                try:
                    response = self.session.get(
                        self.BASE_URL,
                        params=params,
                        headers=headers,
                        timeout=60,
                    )

                    if response.status_code == 401:
                        logger.info("Token expired, refreshing")
                        self._access_token = None
                        self._ensure_token()
                        continue

                    if response.status_code >= 500:
                        logger.warning("EUIPO design search returned %d", response.status_code)
                        api_errors += 1
                        break

                    response.raise_for_status()
                    data = response.json()

                    items = data.get("designs") or data.get("results") or []
                    if not items:
                        break

                    records.extend(items)

                    if len(items) < PAGE_SIZE:
                        break

                    page += 1
                    time.sleep(REQUEST_DELAY)

                except Exception as e:
                    logger.warning("Design search request failed at page %d: %s", page, e)
                    api_errors += 1
                    break

            # Normalize and deduplicate
            all_records: List[Dict[str, Any]] = []
            seen_ids: set = set()

            for raw in records:
                normalized = self._normalize_design(raw)
                if normalized:
                    design_id = normalized.get("application_number")
                    if design_id and design_id not in seen_ids:
                        seen_ids.add(design_id)
                        all_records.append(normalized)

            content_hash = hashlib.md5(
                str(sorted(seen_ids)).encode()
            ).hexdigest()

            if not all_records and api_errors > 0:
                status = "failed"
            elif api_errors > 0:
                status = "partial"
            else:
                status = "success"

            if not all_records and status == "success":
                logger.warning(
                    "EUIPO designs: 0 records returned with no API errors — "
                    "possible silent auth failure or rate-limit (check EUIPO credentials)"
                )

            result = {
                "status": status,
                "records": all_records,
                "record_count": len(all_records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": status, "records": len(all_records)})
            return result

        except Exception as e:
            logger.exception("Failed to fetch EUIPO design data: %s", e)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

    def _ensure_token(self) -> None:
        """Obtain or refresh OAuth2 access token."""
        if self._access_token and time.time() < self._token_expires_at:
            return

        if not self.api_key or not self.secret_key:
            raise RuntimeError("EUIPO_API_KEY and EUIPO_SECRET_KEY required")

        logger.debug("Requesting EUIPO design search access token")
        response = self.session.post(
            self.TOKEN_URL,
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

    @staticmethod
    def _normalize_design(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize EUIPO design response to flat record."""
        application_number = (
            raw.get("applicationNumber")
            or raw.get("application_number")
            or raw.get("designNumber")
        )
        if not application_number:
            return None

        locarno_raw = raw.get("locarnoClasses") or raw.get("locarno_classes") or []
        locarno_classes: List[str] = []
        if isinstance(locarno_raw, list):
            locarno_classes = [str(c) for c in locarno_raw]

        return {
            "application_number": str(application_number),
            "design_title": raw.get("designTitle") or raw.get("title") or raw.get("indication"),
            "applicant_name": raw.get("applicantName") or raw.get("applicant_name") or raw.get("holderName"),
            "applicant_country": raw.get("applicantCountry") or raw.get("applicant_country"),
            "representative_name": raw.get("representativeName") or raw.get("representative_name"),
            "status": raw.get("status") or raw.get("designStatus"),
            "filing_date": raw.get("applicationDate") or raw.get("filing_date"),
            "registration_date": raw.get("registrationDate") or raw.get("registration_date"),
            "expiry_date": raw.get("expiryDate") or raw.get("expiry_date"),
            "publication_date": raw.get("publicationDate") or raw.get("publication_date"),
            "locarno_classes": sorted(set(locarno_classes)) if locarno_classes else None,
            "product_indication": raw.get("productIndication") or raw.get("product_indication"),
            "image_url": raw.get("imageUrl") or raw.get("image_url"),
            "designer_name": raw.get("designerName") or raw.get("designer_name"),
            "number_of_designs": raw.get("numberOfDesigns") or raw.get("number_of_designs"),
        }
