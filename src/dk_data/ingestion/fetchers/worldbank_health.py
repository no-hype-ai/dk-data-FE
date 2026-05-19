"""World Bank Health Indicators fetcher — health expenditure and outcomes.

Fetches country-level health indicators from the World Bank Open Data API.
Primary indicator: SH.XPD.CHEX.GD.ZS (Current health expenditure % of GDP).
Also fetches supplementary indicators for out-of-pocket, per-capita spending,
and life expectancy for cross-validation with WHO GHED data.

API: https://api.worldbank.org/v2/
  Public, no authentication required.
  Endpoint: GET /country/all/indicator/{code}?format=json&per_page=1000&page={N}
  Response: [{"page":1,"pages":N,"total":N,...}, [{country,date,value,...}]]
  Rate limit: polite, no official limit but 0.25s delay used.

Target table: hcs_raw.worldbank_health
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.worldbank.org/v2"
_PAGE_SIZE = 1000
_REQUEST_DELAY = 0.25
_DEFAULT_MAX_RECORDS = 50_000

# World Bank health-related indicator codes
_INDICATORS = [
    "SH.XPD.CHEX.GD.ZS",    # Current health expenditure (% of GDP)
    "SH.XPD.CHEX.PC.CD",     # Current health expenditure per capita (current US$)
    "SH.XPD.OOPC.CH.ZS",     # Out-of-pocket expenditure (% of CHE)
    "SH.XPD.GHED.GD.ZS",     # Domestic general government health expenditure (% of GDP)
    "SP.DYN.LE00.IN",        # Life expectancy at birth, total (years)
    "SH.MED.PHYS.ZS",        # Physicians (per 1,000 people)
    "SH.MED.BEDS.ZS",        # Hospital beds (per 1,000 people)
]


class WorldBankHealthFetcher(BaseFetcher):
    """Fetcher for World Bank health indicators via the v2 REST API.

    Paginates through JSON responses for each indicator code.
    Each record is a dict with country, date (year), indicator, and value.
    Deduplication at load time uses (indicator_code, country_code, year).
    """

    SOURCE_NAME = "worldbank_health"
    BASE_URL = _BASE_URL

    def get_latest_url(self) -> str:
        return (
            f"{_BASE_URL}/country/all/indicator/SH.XPD.CHEX.GD.ZS"
            f"?format=json&per_page={_PAGE_SIZE}&page=1"
        )

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch World Bank health indicator records.

        Keyword Args:
            max_records: Cap total records across all indicators. Default: 50,000.
            indicators: List of indicator codes. Default: health expenditure suite.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: int = int(kwargs.get("max_records", _DEFAULT_MAX_RECORDS))
        indicators: List[str] = list(kwargs.get("indicators", _INDICATORS))

        try:
            all_records: List[Dict[str, Any]] = []

            for indicator_code in indicators:
                if len(all_records) >= max_records:
                    break
                remaining = max_records - len(all_records)
                records = self._fetch_indicator(indicator_code, remaining)
                all_records.extend(records)
                logger.info(
                    "WorldBank: %s -> %d records (total: %d)",
                    indicator_code, len(records), len(all_records),
                )

            content_hash = hashlib.md5(
                json.dumps(len(all_records)).encode()
            ).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": all_records,
                "record_count": len(all_records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(all_records)})
            return result

        except Exception as exc:
            logger.exception("World Bank health fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_indicator(
        self, indicator_code: str, max_records: int
    ) -> List[Dict[str, Any]]:
        """Fetch all pages for a single World Bank indicator."""
        all_values: List[Dict[str, Any]] = []
        page = 1

        while len(all_values) < max_records:
            url = (
                f"{_BASE_URL}/country/all/indicator/{indicator_code}"
                f"?format=json&per_page={_PAGE_SIZE}&page={page}"
            )

            try:
                resp = self.session.get(url, timeout=60)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning(
                    "WorldBank: fetch failed for %s page=%d: %s",
                    indicator_code, page, exc,
                )
                break

            # World Bank API returns [metadata, data_array]
            if not isinstance(data, list) or len(data) < 2:
                logger.warning(
                    "WorldBank: unexpected response format for %s page=%d",
                    indicator_code, page,
                )
                break

            metadata = data[0]
            records = data[1]

            if not records:
                break

            # Normalize records and filter out null values
            for rec in records:
                if rec.get("value") is None:
                    continue
                normalized = {
                    "indicator_code": indicator_code,
                    "indicator_name": (
                        rec.get("indicator", {}).get("value", "")
                        if isinstance(rec.get("indicator"), dict)
                        else str(rec.get("indicator", ""))
                    ),
                    "country_code": (
                        rec.get("country", {}).get("id", "")
                        if isinstance(rec.get("country"), dict)
                        else str(rec.get("country", ""))
                    ),
                    "country_name": (
                        rec.get("country", {}).get("value", "")
                        if isinstance(rec.get("country"), dict)
                        else ""
                    ),
                    "year": rec.get("date", ""),
                    "value": rec.get("value"),
                    "decimal": rec.get("decimal", 0),
                    "_source": "worldbank_health",
                }
                all_values.append(normalized)

            total_pages = metadata.get("pages", 1)
            if page >= total_pages:
                break

            page += 1
            time.sleep(_REQUEST_DELAY)

        return all_values[:max_records]
