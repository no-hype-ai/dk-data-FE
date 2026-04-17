"""OECD Health Statistics fetcher — health expenditure and outcomes data.

Fetches OECD health statistics from the OECD SDMX REST API (v2).
Primary dataset: SHA (System of Health Accounts) — health expenditure by
financing scheme, function, and provider for all OECD member countries.

API: https://sdmx.oecd.org/public/rest/
  Public, no authentication required.
  Endpoint: GET /data/{dataflow}/{key}?format=csv
  The old stats.oecd.org is being deprecated in favour of OECD.Stat Explorer
  backed by SDMX. We use the SDMX-CSV endpoint for bulk download.

  Fallback: JSON endpoint at the same base.

Target table: hcs_raw.oecd_health
"""

import csv
import hashlib
import io
import json
import logging
import time
from typing import Any, Dict, List

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# OECD SDMX REST v2 (replacing stats.oecd.org)
_SDMX_BASE = "https://sdmx.oecd.org/public/rest"
# SHA = System of Health Accounts (health expenditure dataset)
_SHA_DATAFLOW = "OECD.ELS.HD,DSD_SHA@DF_SHA,1.0"
# Key filter: all countries, all financing schemes, all functions, all providers
_SHA_KEY = "....."
_DEFAULT_MAX_RECORDS = 50_000
_CONTENT_LENGTH_LIMIT = 200 * 1024 * 1024  # 200 MB guard
_REQUEST_DELAY = 0.5

# Supplementary dataflows for broader health statistics
_EXTRA_DATAFLOWS = [
    "OECD.ELS.HD,DSD_HEALTH_STAT@DF_HEALTH_STAT,1.0",  # Health Status
]


class OECDHealthFetcher(BaseFetcher):
    """Fetcher for OECD health statistics via SDMX REST API.

    Downloads CSV bulk data for the SHA (System of Health Accounts) dataflow.
    Falls back to paginated JSON if CSV is unavailable.

    Each record is a dict with REF_AREA (country), TIME_PERIOD (year),
    OBS_VALUE, and various dimension codes.
    """

    SOURCE_NAME = "oecd_health"
    BASE_URL = _SDMX_BASE

    def get_latest_url(self) -> str:
        return f"{_SDMX_BASE}/data/{_SHA_DATAFLOW}/{_SHA_KEY}?format=csv"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch OECD health statistics records.

        Keyword Args:
            max_records: Cap total records. Default: 50,000.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: int = int(kwargs.get("max_records", _DEFAULT_MAX_RECORDS))

        try:
            records = self._fetch_sdmx_csv(max_records)

            if not records:
                logger.info("OECD Health: SDMX CSV empty, trying JSON fallback")
                records = self._fetch_sdmx_json(max_records)

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
            logger.exception("OECD Health fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _fetch_sdmx_csv(self, max_records: int) -> List[Dict[str, Any]]:
        """Download OECD SHA dataset as CSV via SDMX REST."""
        url = f"{_SDMX_BASE}/data/{_SHA_DATAFLOW}/{_SHA_KEY}?format=csv"
        logger.info("OECD Health: fetching SDMX CSV from %s", url)

        resp = self.session.get(url, stream=True, timeout=300)
        resp.raise_for_status()

        # C.4 integrity guard
        content_length = resp.headers.get("Content-Length")
        if content_length and int(content_length) > _CONTENT_LENGTH_LIMIT:
            raise ValueError(
                f"OECD CSV too large: {content_length} bytes "
                f"(limit {_CONTENT_LENGTH_LIMIT})"
            )

        raw_bytes = b""
        total = 0
        for chunk in resp.iter_content(chunk_size=65536):
            raw_bytes += chunk
            total += len(chunk)
            if total > _CONTENT_LENGTH_LIMIT:
                raise ValueError(
                    f"OECD CSV download exceeded {_CONTENT_LENGTH_LIMIT} bytes"
                )

        logger.info("OECD Health: downloaded %d bytes CSV", total)

        csv_text = raw_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(csv_text))
        records: List[Dict[str, Any]] = []
        for row in reader:
            if len(records) >= max_records:
                break
            row["_source"] = "oecd_health"
            records.append(dict(row))

        logger.info("OECD Health: parsed %d records from SDMX CSV", len(records))
        return records

    def _fetch_sdmx_json(self, max_records: int) -> List[Dict[str, Any]]:
        """Fallback: fetch OECD data via SDMX JSON endpoint."""
        url = (
            f"{_SDMX_BASE}/data/{_SHA_DATAFLOW}/{_SHA_KEY}"
            f"?format=jsondata&detail=dataonly"
        )
        logger.info("OECD Health: trying SDMX JSON fallback from %s", url)

        try:
            resp = self.session.get(url, timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("OECD Health JSON fallback failed: %s", exc)
            return []

        records: List[Dict[str, Any]] = []
        # SDMX-JSON structure: dataSets[0].observations
        datasets = data.get("dataSets", [])
        if not datasets:
            return records

        observations = datasets[0].get("observations", {})
        # Dimensions are encoded as colon-separated keys
        dimensions = data.get("structure", {}).get("dimensions", {})
        obs_dims = dimensions.get("observation", [])
        series_dims = dimensions.get("series", [])

        for obs_key, obs_values in observations.items():
            if len(records) >= max_records:
                break
            record = {
                "obs_key": obs_key,
                "obs_value": obs_values[0] if obs_values else None,
                "_source": "oecd_health",
            }
            records.append(record)

        logger.info("OECD Health: parsed %d records from SDMX JSON", len(records))
        return records
