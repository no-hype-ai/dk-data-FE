"""PharmGKB bulk download fetcher — chemicals TSV.

Feature: 019-cms-puf-platform-reconciliation

PharmGKB provides pharmacogenomics data (drug-gene associations, clinical
annotations, dosing guidelines, variant annotations).

The paginated REST API (GET /data/chemical?pageSize=...) was removed; the
endpoint now only supports single-entity lookups.  Bulk data is available
via the download API:

  GET https://api.pharmgkb.org/v1/download/file/data/chemicals.zip
    → ZIP containing chemicals.tsv (TSV, ~10 k chemicals)

Authentication is not required for the download endpoint.

Each row in chemicals.tsv becomes one record dict in the output.
"""

import csv
import hashlib
import io
import logging
import zipfile
from typing import Any, Dict, List

from .base import BaseFetcher

logger = logging.getLogger(__name__)

CHEMICALS_DOWNLOAD_URL = (
    "https://api.pharmgkb.org/v1/download/file/data/chemicals.zip"
)
CHEMICALS_TSV_NAME = "chemicals.tsv"


class PharmGKBFetcher(BaseFetcher):
    """Fetcher for PharmGKB chemical data via bulk TSV download."""

    SOURCE_NAME = "pharmgkb"
    BASE_URL = "https://api.pharmgkb.org"

    def get_latest_url(self) -> str:
        return CHEMICALS_DOWNLOAD_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download the PharmGKB chemicals ZIP and parse the TSV.

        Returns:
            Dict with keys:
                status        — "success", "failed", or "source_unavailable"
                records       — list of row dicts (one per chemical)
                record_count  — len(records)
                hash          — SHA-256 of the ZIP content
                error         — present only on failure
        """
        try:
            logger.info("Downloading PharmGKB chemicals ZIP from %s", CHEMICALS_DOWNLOAD_URL)
            resp = self.session.get(CHEMICALS_DOWNLOAD_URL, timeout=120)
            resp.raise_for_status()

            content = resp.content
            content_hash = hashlib.sha256(content).hexdigest()

            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                tsv_name = next(
                    (n for n in zf.namelist() if n.endswith(".tsv")),
                    None,
                )
                if tsv_name is None:
                    raise ValueError(
                        f"No .tsv file found in PharmGKB chemicals ZIP: {zf.namelist()}"
                    )
                with zf.open(tsv_name) as f:
                    records = self._parse_tsv(f)

            logger.info("PharmGKB: parsed %d chemicals from %s", len(records), tsv_name)
            result: Dict[str, Any] = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as exc:
            logger.exception("PharmGKB fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_tsv(file_obj) -> List[Dict[str, Any]]:
        """Parse the chemicals.tsv into a list of record dicts.

        Column names are normalised to lowercase with underscores.
        """
        import sys
        csv.field_size_limit(sys.maxsize)
        text = file_obj.read().decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text), delimiter="\t")
        records: List[Dict[str, Any]] = []
        for row in reader:
            # Normalise keys: lowercase, spaces → underscores
            record = {
                k.strip().lower().replace(" ", "_"): (v.strip() if v else None)
                for k, v in row.items()
            }
            records.append(record)
        return records
