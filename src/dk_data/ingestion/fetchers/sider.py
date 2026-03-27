"""SIDER Side Effect Resource Data Fetcher.

SIDER (Side Effect Resource) contains drug side effect information extracted
from public drug package inserts (drug labels).

Source: http://sideeffects.embl.de/
Data files (all TSV, no authentication required):

  meddra_all_se.tsv — all side effects per drug (4 columns):
    stitch_id_flat | stitch_id_stereo | umls_cui_side_effect | side_effect_name

  meddra_freq.tsv — side effects with frequency information (10 columns):
    stitch_id_flat | stitch_id_stereo | umls_cui_side_effect | placebo |
    frequency | lower_bound_freq | upper_bound_freq | meddra_concept_type |
    umls_cui_from_label | side_effect_name

The fetcher downloads both files and merges rows by STITCH ID + UMLS CUI,
preserving exact column header names for the bronze SQL model.
"""

import csv
import gzip
import hashlib
import io
import logging
from typing import Any, Dict, List

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class SIDERFetcher(BaseFetcher):
    """Fetcher for SIDER drug side effect data."""

    SOURCE_NAME = "sider"
    BASE_URL = "http://sideeffects.embl.de/media/files"

    # SIDER data file URLs
    ALL_SE_URL = f"{BASE_URL}/meddra_all_se.tsv.gz"
    FREQ_URL = f"{BASE_URL}/meddra_freq.tsv.gz"

    # Maximum records per run
    MAX_RECORDS = 100_000

    # Column definitions matching exact SIDER TSV headers
    ALL_SE_COLUMNS = [
        "stitch_id_flat",
        "stitch_id_stereo",
        "umls_cui_side_effect",
        "side_effect_name",
    ]

    FREQ_COLUMNS = [
        "stitch_id_flat",
        "stitch_id_stereo",
        "umls_cui_side_effect",
        "placebo",
        "frequency",
        "lower_bound_freq",
        "upper_bound_freq",
        "meddra_concept_type",
        "umls_cui_from_label",
        "side_effect_name",
    ]

    def get_latest_url(self) -> str:
        return self.FREQ_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch SIDER side effect data.

        Keyword Args:
            max_records: Maximum rows to load. Defaults to MAX_RECORDS.
            source: Which file to load: 'freq' (default) or 'all_se' or 'both'.

        Returns:
            Dict with keys: status, records, hash, error (on failure).
        """
        max_records = kwargs.get("max_records", self.MAX_RECORDS)
        source = kwargs.get("source", "freq")

        try:
            records: List[Dict[str, Any]] = []

            if source in ("freq", "both"):
                freq_records = self._fetch_file(
                    self.FREQ_URL,
                    self.FREQ_COLUMNS,
                    max_records,
                    source_file="meddra_freq.tsv",
                )
                records.extend(freq_records)

            if source in ("all_se", "both"):
                remaining = max_records - len(records)
                if remaining > 0:
                    all_se_records = self._fetch_file(
                        self.ALL_SE_URL,
                        self.ALL_SE_COLUMNS,
                        remaining,
                        source_file="meddra_all_se.tsv",
                    )
                    records.extend(all_se_records)

            content_hash = hashlib.md5(
                str(len(records)).encode()
            ).hexdigest() if records else None

            result = {
                "status": "success",
                "records": records,
                "hash": content_hash,
            }
            self.log_fetch_result({**result, "records": len(records)})
            return result

        except Exception as e:
            logger.exception(f"SIDER fetch failed: {e}")
            result = {"status": "failed", "records": [], "hash": None, "error": str(e)}
            self.log_fetch_result(result)
            return result

    def _fetch_file(
        self,
        url: str,
        columns: List[str],
        max_records: int,
        source_file: str,
    ) -> List[Dict[str, Any]]:
        """Download and parse one SIDER TSV.gz file."""
        logger.info(f"Downloading SIDER file: {url}")
        response = self.session.get(url, stream=True, timeout=300)
        response.raise_for_status()

        raw_bytes = response.content
        logger.info(f"Downloaded {len(raw_bytes) / 1024 / 1024:.1f} MB")

        records: List[Dict[str, Any]] = []

        with gzip.open(io.BytesIO(raw_bytes), "rt", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f, delimiter="\t")

            for row in reader:
                if len(records) >= max_records:
                    break

                # SIDER TSV files have no header row — use positional columns
                if len(row) < len(columns):
                    continue  # skip malformed rows

                record: Dict[str, Any] = {}
                for col, val in zip(columns, row):
                    stripped = val.strip()
                    record[col] = stripped if stripped else None

                # stitch_id_flat is the primary key — skip if missing
                if not record.get("stitch_id_flat"):
                    continue

                # Tag which source file this came from for bronze traceability
                record["source_file"] = source_file

                records.append(record)

        logger.info(f"Parsed {len(records)} records from {source_file}")
        return records
