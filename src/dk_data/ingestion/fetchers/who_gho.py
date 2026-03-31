"""WHO GHO fetcher — World Health Organization Global Health Observatory data.

Fetches health indicator definitions from the WHO GHO OData REST API.
The GHO provides ~2,400 global health indicators covering mortality,
morbidity, nutrition, NCD risk factors, and health service coverage.

API: https://ghoapi.azureedge.net/api (OData v4)
  Public, no authentication required.
  Endpoint 1 (indicators): GET /Indicator → all ~2,400 indicator definitions
  Endpoint 2 (data): GET /{IndicatorCode}?$top=N&$skip=M → indicator values
  Response: {"value": [{...}]}
  Rate limit: polite, 0.5s delay.

Two fetch modes:
  - indicators only (fetch_indicators=True, default): fetch all indicator
    definitions (~2,400 records). Fast, suitable for daily refresh.
  - full_backfill=True: fetch indicator definitions + data values for each
    indicator. Much larger dataset — use for initial population only.

Stores one JSONB record per indicator (or per data value) in mol_raw.who_gho.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_BASE_URL = "https://ghoapi.azureedge.net/api"
_PAGE_SIZE = 1000
_REQUEST_DELAY = 0.5
_DEFAULT_MAX_RECORDS = 10_000


class WHOGHOFetcher(BaseFetcher):
    """Fetcher for WHO GHO health indicator data via the OData REST API.

    Default mode fetches all indicator definitions (fast, ~2400 records).
    Full backfill mode additionally fetches data values per indicator.
    Each record is a dict keyed by IndicatorCode.
    Deduplication at load time uses an expression index on
    response_body->>'IndicatorCode'.
    """

    SOURCE_NAME = "who_gho"
    BASE_URL = _BASE_URL

    def get_latest_url(self) -> str:
        return f"{_BASE_URL}/Indicator"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch WHO GHO indicator records.

        Keyword Args:
            fetch_indicators: If True (default), fetch only indicator
                definitions (~2,400). Fast mode for daily refresh.
            full_backfill: If True, also fetch data values per indicator.
                Warning: large dataset, use only for initial population.
            max_records: Cap total records. Default: 10,000.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: int = int(kwargs.get("max_records", _DEFAULT_MAX_RECORDS))
        full_backfill: bool = bool(kwargs.get("full_backfill", False))

        try:
            records = self._fetch_indicators(
                max_records=max_records,
                include_data=full_backfill,
            )
            content_hash = hashlib.md5(
                json.dumps(len(records)).encode()
            ).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("WHO GHO fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_indicators(
        self, max_records: int, include_data: bool
    ) -> List[Dict[str, Any]]:
        """Fetch WHO GHO indicator definitions (and optionally data values)."""
        # Step 1: fetch all indicator definitions
        indicators_url = f"{_BASE_URL}/Indicator"
        logger.info("WHO GHO: fetching indicator definitions")

        try:
            resp = self.session.get(indicators_url, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error("WHO GHO: failed to fetch indicator list: %s", exc)
            return []

        all_indicators: List[Dict[str, Any]] = data.get("value", [])
        logger.info("WHO GHO: %d indicator definitions fetched", len(all_indicators))

        if not include_data:
            return all_indicators[:max_records]

        # Step 2 (full backfill only): fetch data values per indicator
        all_records: List[Dict[str, Any]] = list(all_indicators)
        remaining = max_records - len(all_indicators)

        for indicator in all_indicators:
            if remaining <= 0:
                break
            code = indicator.get("IndicatorCode")
            if not code:
                continue

            values = self._fetch_indicator_data(code, max_values=min(1000, remaining))
            all_records.extend(values)
            remaining -= len(values)

            logger.debug(
                "WHO GHO: %s → %d data values (running total=%d)",
                code, len(values), len(all_records),
            )
            time.sleep(_REQUEST_DELAY)

        logger.info("WHO GHO: %d total records fetched", len(all_records))
        return all_records[:max_records]

    def _fetch_indicator_data(
        self, indicator_code: str, max_values: int
    ) -> List[Dict[str, Any]]:
        """Fetch data values for a single indicator using OData pagination."""
        all_values: List[Dict[str, Any]] = []
        skip = 0

        while len(all_values) < max_values:
            remaining = max_values - len(all_values)
            top = min(_PAGE_SIZE, remaining)
            url = f"{_BASE_URL}/{indicator_code}?$top={top}&$skip={skip}"

            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code == 404:
                    break
                resp.raise_for_status()
                page_data = resp.json()
            except Exception as exc:
                logger.debug(
                    "WHO GHO: data fetch failed for %s skip=%d: %s",
                    indicator_code, skip, exc,
                )
                break

            values = page_data.get("value", [])
            if not values:
                break

            # Tag each data record with the indicator code for routing
            for v in values:
                v["IndicatorCode"] = indicator_code

            all_values.extend(values)

            if len(values) < top:
                break

            skip += top
            time.sleep(_REQUEST_DELAY)

        return all_values
