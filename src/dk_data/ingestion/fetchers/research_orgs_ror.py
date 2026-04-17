"""Research Organization Registry (ROR) fetcher — Zenodo JSON data dump.

ROR publishes versioned data dumps on Zenodo under the ror-data community.
Each release is a ZIP containing a single JSON file with all research
organisations (~110k records).

Discovery URL (latest release):
  https://zenodo.org/api/records?communities=ror-data&sort=mostrecent&size=1

The response contains a download link for the ZIP file. Inside is a JSON
file (v2 schema) with the full ROR dataset.

Stores one JSONB record per organisation in hcp_raw.research_orgs_ror.
"""

import hashlib
import io
import json
import logging
import zipfile
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_ZENODO_API_URL = (
    "https://zenodo.org/api/records?communities=ror-data&sort=mostrecent&size=1"
)


class ResearchOrgsRORFetcher(BaseFetcher):
    """Fetcher for ROR research organisation data via Zenodo data dump."""

    SOURCE_NAME = "research_orgs_ror"
    BASE_URL = "https://zenodo.org"

    def get_latest_url(self) -> str:
        return _ZENODO_API_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Discover the latest ROR data dump on Zenodo, download and parse.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: Optional[int] = kwargs.get("max_records")

        try:
            # Step 1: discover latest release
            download_url = self._discover_latest_dump_url()
            logger.info("ROR: latest dump URL: %s", download_url)

            # Step 2: download the ZIP
            logger.info("ROR: downloading data dump from %s", download_url)
            resp = self.session.get(download_url, timeout=300, stream=True)
            resp.raise_for_status()

            content = resp.content
            content_hash = hashlib.sha256(content).hexdigest()

            # Step 3: extract and parse
            records = self._extract_and_parse(content, max_records)

            logger.info("ROR: parsed %d organisation records", len(records))

            if not records:
                msg = "ROR: parsed 0 records — treating as source_unavailable"
                logger.warning(msg)
                result: Dict[str, Any] = {
                    "status": "source_unavailable",
                    "records": [],
                    "record_count": 0,
                    "hash": None,
                    "error": msg,
                }
                self.log_fetch_result(result)
                return result

            result = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("ROR fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _discover_latest_dump_url(self) -> str:
        """Query Zenodo API to find the download URL for the latest ROR dump."""
        resp = self.session.get(_ZENODO_API_URL, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            raise ValueError("ROR: no records found in Zenodo ror-data community")

        latest = hits[0]
        files = latest.get("files", [])

        # Find the JSON ZIP file (the main data dump)
        for f in files:
            key = f.get("key", "")
            if key.endswith(".zip") and "ror" in key.lower():
                link = f.get("links", {}).get("self")
                if link:
                    return link

        # Fallback: just take the first ZIP
        for f in files:
            if f.get("key", "").endswith(".zip"):
                link = f.get("links", {}).get("self")
                if link:
                    return link

        raise ValueError(
            f"ROR: no ZIP file found in latest Zenodo record; "
            f"files: {[f.get('key') for f in files]}"
        )

    @staticmethod
    def _extract_and_parse(
        content: bytes, max_records: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Extract the JSON from the ZIP and return organisation records."""
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            # Find the JSON file inside
            json_names = [n for n in zf.namelist() if n.endswith(".json")]
            if not json_names:
                raise ValueError(
                    f"ROR: no JSON file in ZIP; contents: {zf.namelist()}"
                )
            json_name = json_names[0]
            logger.info("ROR: extracting %s", json_name)

            with zf.open(json_name) as f:
                data = json.load(f)

        # ROR v2 schema: top-level list of organisation objects
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            # Some versions wrap in a dict
            records = data.get("items", data.get("organizations", data.get("data", [])))
            if not isinstance(records, list):
                records = [data]
        else:
            records = []

        if max_records is not None:
            records = records[:max_records]

        return records
