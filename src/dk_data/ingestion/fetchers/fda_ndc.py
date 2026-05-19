"""FDA NDC fetcher — National Drug Code directory via bulk download.

Downloads the full NDC dataset from the openFDA bulk export:
  https://download.open.fda.gov/drug/ndc/drug-ndc-0001-of-0001.json.zip

The bulk file (~26 MB compressed, ~133 K records) is updated daily and
eliminates the API pagination/skip-limit issues:
  - No per-partition alphabetic splitting needed
  - No Lucene query syntax errors
  - No silent record loss from the 25,000-skip cap

API docs: https://open.fda.gov/apis/drug/ndc/download/
Stores one JSONB record per NDC product in mol_raw.fda_ndc (migration 126).
"""

import hashlib
import io
import json
import logging
import zipfile
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_BULK_URL = "https://download.open.fda.gov/drug/ndc/drug-ndc-0001-of-0001.json.zip"
_BULK_JSON_NAME = "drug-ndc-0001-of-0001.json"


class FDANDCFetcher(BaseFetcher):
    """Fetcher for FDA National Drug Code directory via openFDA bulk download.

    Downloads the full daily bulk export zip (~26 MB), extracts all NDC
    product records, and returns them for loading into mol_raw.fda_ndc.
    Replaces the previous alphabetic-partition API approach which had invalid
    Lucene syntax and silent record loss above the 25,000-skip limit.
    """

    SOURCE_NAME = "fda_ndc"
    BASE_URL = "https://download.open.fda.gov"

    def get_latest_url(self) -> str:
        return _BULK_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download the FDA NDC bulk JSON, parse, and return all product records.

        Keyword Args:
            max_records: Cap total records returned (for testing). Default: all.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: Optional[int] = kwargs.get("max_records")

        try:
            records = self._download_and_parse(max_records=max_records)
            content_hash = hashlib.md5(str(len(records)).encode()).hexdigest()

            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("FDA NDC bulk fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _download_and_parse(self, max_records: Optional[int]) -> List[Dict[str, Any]]:
        """Download the bulk zip, extract the JSON, return results list."""
        logger.info("FDA NDC: downloading bulk file from %s", _BULK_URL)

        resp = self.session.get(_BULK_URL, timeout=300, stream=True)
        resp.raise_for_status()

        raw_bytes = resp.content
        logger.info("FDA NDC: downloaded %d bytes", len(raw_bytes))

        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            # Pick the first JSON file in the archive (name may vary across releases)
            json_names = [n for n in zf.namelist() if n.endswith(".json")]
            if not json_names:
                raise ValueError(f"No JSON file found in NDC bulk zip; contents: {zf.namelist()}")
            json_name = json_names[0]
            logger.info("FDA NDC: extracting %s", json_name)
            with zf.open(json_name) as f:
                data = json.load(f)

        results: List[Dict[str, Any]] = data.get("results", [])
        logger.info("FDA NDC: bulk file contains %d records", len(results))

        if max_records is not None:
            results = results[:max_records]

        return results
