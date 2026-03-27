"""BindingDB Data Fetcher.

BindingDB provides drug-target binding affinity measurements.
Data is distributed as tab-separated value (TSV) files.

Source: https://www.bindingdb.org/bind/downloads.jsp
Download: BindingDB_All.tsv.zip (full dataset)

The fetcher downloads and parses the TSV, yielding one dict per row
with keys matching the TSV column headers verbatim (e.g., "Ki (nM)").
This preserves exact field names so the bronze SQL model can reference
them correctly in response_body JSONB.
"""

import csv
import hashlib
import io
import logging
import zipfile
from typing import Any, Dict, List

from .base import BaseFetcher

logger = logging.getLogger(__name__)


class BindingDBFetcher(BaseFetcher):
    """Fetcher for BindingDB binding affinity data."""

    SOURCE_NAME = "bindingdb"
    BASE_URL = "https://www.bindingdb.org/bind/downloads.jsp"

    # Full dataset download URL (updated annually by BindingDB)
    DOWNLOAD_URL = "https://www.bindingdb.org/bind/BindingDB_All.tsv.zip"

    # Maximum records to load per run (prevents memory exhaustion)
    # BindingDB has ~2.8M rows; load in manageable batches
    MAX_RECORDS = 50_000

    # Key columns to include in the JSONB record
    # These are the exact TSV header names BindingDB uses
    REQUIRED_COLUMNS = {
        "BindingDB Reactant_set_id",
        "Ligand InChIKey",
        "Ligand SMILES",
        "PubChem CID",
        "ChEMBL ID of Ligand",
        "Target Name Assigned by Curator or DataSource",
        "Target Source Organism According to Curator or DataSource",
        "UniProt (SwissProt) Primary ID of Target Chain",
        "Ki (nM)",
        "IC50 (nM)",
        "Kd (nM)",
        "EC50 (nM)",
        "kon (M-1-s-1)",
        "koff (s-1)",
        "pH",
        "Temp (C)",
        "Curation/DataSource",
        "Article DOI",
        "PMID",
        "PDB ID(s) for Ligand-Target Complex",
    }

    def get_latest_url(self) -> str:
        return self.DOWNLOAD_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch BindingDB binding affinity data.

        Keyword Args:
            max_records: Maximum rows to load. Defaults to MAX_RECORDS.
            require_affinity: If True, skip rows with no Ki/IC50/Kd/EC50 value.

        Returns:
            Dict with keys: status, records, hash, error (on failure).
        """
        max_records = kwargs.get("max_records", self.MAX_RECORDS)
        require_affinity = kwargs.get("require_affinity", True)

        try:
            records = self._download_and_parse(max_records, require_affinity)

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
            logger.exception(f"BindingDB fetch failed: {e}")
            result = {"status": "failed", "records": [], "hash": None, "error": str(e)}
            self.log_fetch_result(result)
            return result

    def _download_and_parse(
        self,
        max_records: int,
        require_affinity: bool,
    ) -> List[Dict[str, Any]]:
        """Download the BindingDB TSV zip and parse rows into dicts."""
        logger.info(f"Downloading BindingDB dataset from {self.DOWNLOAD_URL}")
        response = self.session.get(self.DOWNLOAD_URL, stream=True, timeout=600)
        response.raise_for_status()

        raw_bytes = response.content
        logger.info(f"Downloaded {len(raw_bytes) / 1024 / 1024:.1f} MB")

        records: List[Dict[str, Any]] = []

        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            # The zip contains a single TSV file
            tsv_names = [n for n in zf.namelist() if n.endswith(".tsv")]
            if not tsv_names:
                raise ValueError("No TSV file found in BindingDB zip archive")

            tsv_name = tsv_names[0]
            logger.info(f"Parsing {tsv_name}")

            with zf.open(tsv_name) as tsv_bytes:
                text = io.TextIOWrapper(tsv_bytes, encoding="utf-8", errors="replace")
                reader = csv.DictReader(text, delimiter="\t")

                affinity_cols = {"Ki (nM)", "IC50 (nM)", "Kd (nM)", "EC50 (nM)"}

                for row in reader:
                    if len(records) >= max_records:
                        break

                    # Skip rows with no usable affinity measurement
                    if require_affinity:
                        has_affinity = any(
                            row.get(col, "").strip() not in ("", "N/A", "NA", "None")
                            for col in affinity_cols
                        )
                        if not has_affinity:
                            continue

                    # Skip rows without a BindingDB record ID
                    if not row.get("BindingDB Reactant_set_id", "").strip():
                        continue

                    # Build record with only the required columns (to keep JSONB manageable)
                    record: Dict[str, Any] = {}
                    for col in self.REQUIRED_COLUMNS:
                        val = row.get(col, "").strip()
                        record[col] = val if val not in ("", "N/A", "NA", "None") else None

                    records.append(record)

        logger.info(f"Parsed {len(records)} BindingDB records")
        return records
