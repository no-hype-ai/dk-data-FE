"""FDA Orange Book fetcher — products, patents, and exclusivity.

The FDA Orange Book identifies drug products approved under the FD&C Act
and lists patent and exclusivity information critical for market entry timing.

Three pipe-delimited text files are published at stable FDA media URLs:
  products.txt    — NDA/ANDA products with applicant, active ingredient, form
  patent.txt      — patent numbers, expiry dates per NDA/ANDA
  exclusivity.txt — exclusivity codes and expiry dates per NDA/ANDA

All three files are downloaded and merged into a single records list tagged
by _file_type ('products', 'patents', 'exclusivity').

Stores one JSONB record per row in mol_raw.orange_book (migration 096).
"""

import csv
import hashlib
import io
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_FILES = {
    "products":    "https://www.fda.gov/media/76860/download",
    "patents":     "https://www.fda.gov/media/76861/download",
    "exclusivity": "https://www.fda.gov/media/76862/download",
}


class OrangeBookFetcher(BaseFetcher):
    """Fetcher for FDA Orange Book products, patents, and exclusivity."""

    SOURCE_NAME = "orange_book"
    BASE_URL = "https://www.fda.gov/media"

    def get_latest_url(self) -> str:
        return _FILES["products"]

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download all three Orange Book files and return combined record list.

        Each record dict has a ``_file_type`` key (products/patents/exclusivity)
        so the loader can tag records by their origin.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: Optional[int] = kwargs.get("max_records")
        all_records: List[Dict[str, Any]] = []
        combined_hash = hashlib.md5()
        errors: List[str] = []

        for file_type, url in _FILES.items():
            try:
                logger.info("OrangeBook: downloading %s from %s", file_type, url)
                resp = self.session.get(url, timeout=120, allow_redirects=True)
                resp.raise_for_status()

                content = resp.content
                combined_hash.update(content)

                records = self._parse_pipe_delimited(content, file_type)
                logger.info("OrangeBook: parsed %d %s records", len(records), file_type)
                all_records.extend(records)

                if max_records and len(all_records) >= max_records:
                    all_records = all_records[:max_records]
                    break

            except Exception as exc:
                msg = f"OrangeBook: {file_type} download failed: {exc}"
                logger.warning(msg)
                errors.append(msg)

        if not all_records and errors:
            result = {"status": "source_unavailable", "records": [], "record_count": 0, "hash": None, "error": "; ".join(errors)}
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

    def _parse_pipe_delimited(self, content: bytes, file_type: str) -> List[Dict[str, Any]]:
        """Parse an Orange Book pipe-delimited text file."""
        text = content.decode("utf-8", errors="replace")
        # FDA Orange Book files use '~' as delimiter in newer releases, '|' in older
        sample = text[:500]
        delimiter = "~" if "~" in sample else "|"

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        records: List[Dict[str, Any]] = []
        for row in reader:
            rec = {k.strip(): (v.strip() or None) for k, v in row.items() if k}
            rec["_file_type"] = file_type
            records.append(rec)
        return records
