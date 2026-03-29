"""Therapeutic Target Database (TTD) bulk download fetcher.

TTD (http://db.idrblab.net/ttd/) provides information on therapeutic targets
and drugs, especially valuable for biologics and small-molecule target data.

TTD publishes flat-file bulk downloads at:
  https://db.idrblab.net/ttd/sites/default/files/ttd_database/

Key files downloaded:
  P1-01-TTD_target_download.txt   — target IDs, names, type, status
  P1-04-Drug_synonyms.txt         — drug IDs, synonyms, CAS, InChIKey
  P1-05-Drug_target.txt           — drug→target associations
  P2-01-TTD_uniprot_all.txt       — UniProt ID mappings for targets

Files use an unusual key-value format:
  TTDDRUID  D0J0ZN                ← block header
  DRUGNAME  Trastuzumab           ← field name + value
  ...
  DRUGINFO  <blank line separator>

The fetcher parses these flat files into list-of-dict records.
Stores records in mol_raw.ttd (migration 096).
"""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_BASE_URL = "https://db.idrblab.net/ttd/sites/default/files/ttd_database"

_DOWNLOAD_FILES = {
    "targets":      f"{_BASE_URL}/P1-01-TTD_target_download.txt",
    "drug_synonyms": f"{_BASE_URL}/P1-04-Drug_synonyms.txt",
    "drug_target":  f"{_BASE_URL}/P1-05-Drug_target.txt",
    "uniprot":      f"{_BASE_URL}/P2-01-TTD_uniprot_all.txt",
}


class TTDFetcher(BaseFetcher):
    """Fetcher for TTD bulk download files."""

    SOURCE_NAME = "ttd"
    BASE_URL = _BASE_URL

    def get_latest_url(self) -> str:
        return _DOWNLOAD_FILES["targets"]

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download TTD flat files and parse into record dicts.

        Each record dict includes a ``_file_type`` key indicating which
        TTD file it originated from.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
            status='source_unavailable' when all file downloads fail.
        """
        max_records: Optional[int] = kwargs.get("max_records")
        all_records: List[Dict[str, Any]] = []
        combined_hash = hashlib.md5()
        errors: List[str] = []

        for file_type, url in _DOWNLOAD_FILES.items():
            try:
                logger.info("TTD: downloading %s from %s", file_type, url)
                resp = self.session.get(url, timeout=120)
                if resp.status_code == 404:
                    logger.debug("TTD: 404 for %s, skipping", file_type)
                    continue
                resp.raise_for_status()

                content = resp.content
                combined_hash.update(content)

                text = content.decode("utf-8", errors="replace")
                records = self._parse_ttd_flat_file(text, file_type)
                logger.info("TTD: parsed %d records from %s", len(records), file_type)
                all_records.extend(records)

                if max_records and len(all_records) >= max_records:
                    all_records = all_records[:max_records]
                    break

            except Exception as exc:
                msg = f"TTD: {file_type} download failed: {exc}"
                logger.warning(msg)
                errors.append(msg)

        if not all_records:
            msg = "TTD: no data retrieved from any file. " + "; ".join(errors)
            logger.warning(msg)
            result = {"status": "source_unavailable", "records": [], "record_count": 0, "hash": None, "error": msg}
            self.log_fetch_result(result)
            return result

        result: Dict[str, Any] = {
            "status": "success",
            "records": all_records,
            "record_count": len(all_records),
            "hash": combined_hash.hexdigest(),
        }
        if errors:
            result["partial_errors"] = errors
        self.log_fetch_result({"status": "success", "records": len(all_records)})
        return result

    def _parse_ttd_flat_file(self, text: str, file_type: str) -> List[Dict[str, Any]]:
        """Parse a TTD key-value flat file into list of record dicts.

        TTD files use a block format:
          ID_FIELD  <entity_id>
          FIELD1    value1
          FIELD2    value2
          <blank line = end of block>
        """
        records: List[Dict[str, Any]] = []
        current: Dict[str, Any] = {}

        for line in text.splitlines():
            line = line.rstrip()
            if not line:
                # Blank line = end of block
                if current:
                    current["_file_type"] = file_type
                    records.append(current)
                    current = {}
                continue

            # Tab-separated key-value; some files use multiple tabs
            parts = re.split(r"\t+", line, maxsplit=1)
            if len(parts) == 2:
                key, value = parts[0].strip(), parts[1].strip()
                if key and key not in ("TTDDRUID", "TARGETID"):
                    # For duplicate keys, append a list
                    if key in current:
                        existing = current[key]
                        if isinstance(existing, list):
                            existing.append(value)
                        else:
                            current[key] = [existing, value]
                    else:
                        current[key] = value
                elif key in ("TTDDRUID", "TARGETID"):
                    current["_id"] = value
            elif len(parts) == 1 and parts[0]:
                # Header-only line (the entity ID line format varies)
                current.setdefault("_raw_line", parts[0])

        # Flush last block
        if current:
            current["_file_type"] = file_type
            records.append(current)

        return records
