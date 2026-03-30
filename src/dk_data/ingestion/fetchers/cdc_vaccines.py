"""CDC vaccine data fetcher — CVX codes, manufacturer info, vaccine schedules.

CDC provides standardized vaccine data via:
  1. CVX code list — standardized vaccine codes used in immunization records
     https://www2a.cdc.gov/vaccines/iis/iisstandards/vaccines.asp?rpt=cvx
     (HTML table format)

  2. CDC MMWR immunization schedule (structured JSON via CDC Open Data Portal)
     https://data.cdc.gov/resource/fhky-rtsk.json

  3. NLM/HL7 CVX vocabulary via FHIR CodeSystem
     https://fhir.cdc.gov/eicr/api/R4/CodeSystem/cvx

Strategy: fetch CVX codes via the CDC data API (JSON, no scraping required)
plus the FHIR CodeSystem for structured terminology.

Stores records in mol_raw.cdc_vaccines (migration 096).
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# CDC Open Data Portal — CVX code list
_CDC_DATA_API = "https://data.cdc.gov/resource"
_CVX_DATASET_ID = "fhky-rtsk"          # Vaccine Administered (CVX) codes
_MVX_DATASET_ID = "n6hk-4tzf"          # Manufacturer (MVX) codes
_CDC_API_LIMIT = 1000

# Fallback: NLM FHIR CodeSystem for CVX
_FHIR_CVX_URL = "https://clinicaltables.nlm.nih.gov/api/cvx_codes/v3/search?terms=&maxList=500"


class CDCVaccinesFetcher(BaseFetcher):
    """Fetcher for CDC vaccine CVX/MVX codes and schedule data."""

    SOURCE_NAME = "cdc_vaccines"
    BASE_URL = "https://data.cdc.gov"

    def get_latest_url(self) -> str:
        return f"{_CDC_DATA_API}/{_CVX_DATASET_ID}.json?$limit={_CDC_API_LIMIT}&$offset=0"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch CDC CVX vaccine codes, MVX manufacturer codes, and schedule data.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        try:
            all_records: List[Dict[str, Any]] = []

            # Fetch CVX codes
            cvx_records = self._fetch_socrata_dataset(_CVX_DATASET_ID, "cvx")
            all_records.extend(cvx_records)
            logger.info("CDCVaccines: %d CVX records", len(cvx_records))

            # Fetch MVX manufacturer codes
            mvx_records = self._fetch_socrata_dataset(_MVX_DATASET_ID, "mvx")
            all_records.extend(mvx_records)
            logger.info("CDCVaccines: %d MVX records", len(mvx_records))

            # Fallback to NLM FHIR if CDC API returned nothing
            if not all_records:
                logger.info("CDCVaccines: CDC API returned no data, trying NLM FHIR")
                all_records = self._fetch_nlm_fhir()

            if not all_records:
                msg = "CDCVaccines: no data from any source"
                logger.warning(msg)
                result = {"status": "source_unavailable", "records": [], "record_count": 0, "hash": None, "error": msg}
                self.log_fetch_result(result)
                return result

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
            logger.exception("CDCVaccines fetch failed: %s", exc)
            result = {"status": "failed", "records": [], "record_count": 0, "hash": None, "error": str(exc)}
            self.log_fetch_result(result)
            return result

    def _fetch_socrata_dataset(self, dataset_id: str, record_type: str) -> List[Dict[str, Any]]:
        """Fetch all rows from a CDC Open Data Portal (Socrata) dataset."""
        records: List[Dict[str, Any]] = []
        offset = 0

        while True:
            url = f"{_CDC_DATA_API}/{dataset_id}.json"
            params = {"$limit": _CDC_API_LIMIT, "$offset": offset}
            try:
                resp = self.session.get(url, params=params, timeout=60)
                if resp.status_code == 404:
                    logger.debug("CDCVaccines: dataset %s not found (404)", dataset_id)
                    break
                resp.raise_for_status()
                page = resp.json()
            except Exception as exc:
                logger.warning("CDCVaccines: failed to fetch %s at offset %d: %s", dataset_id, offset, exc)
                break

            if not page:
                break

            for row in page:
                row["_record_type"] = record_type
                records.append(row)

            if len(page) < _CDC_API_LIMIT:
                break

            offset += _CDC_API_LIMIT
            time.sleep(0.2)

        return records

    def _fetch_nlm_fhir(self) -> List[Dict[str, Any]]:
        """Fallback: fetch CVX codes from NLM clinical tables API."""
        try:
            resp = self.session.get(_FHIR_CVX_URL, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            # NLM response: [total, [codes], ..., [[code, description], ...]]
            if isinstance(data, list) and len(data) >= 4 and isinstance(data[3], list):
                records = []
                for item in data[3]:
                    if isinstance(item, list) and len(item) >= 2:
                        records.append({"cvx_code": item[0], "description": item[1], "_record_type": "cvx_nlm"})
                return records
        except Exception as exc:
            logger.warning("CDCVaccines: NLM FHIR fallback failed: %s", exc)
        return []
