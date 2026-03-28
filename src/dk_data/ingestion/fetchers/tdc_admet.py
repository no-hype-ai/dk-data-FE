"""Therapeutics Data Commons (TDC) ADMET Dataset Fetcher.

Feature: 019-cms-puf-platform-reconciliation

Fetches ADMET (Absorption, Distribution, Metabolism, Excretion, Toxicity)
benchmark datasets from the Therapeutics Data Commons project hosted on
GitHub (mims-harvard/TDC).

Each dataset is a TSV file with columns:
    Drug_ID   — compound identifier
    Drug      — SMILES string
    Y         — label or continuous value (endpoint measurement)
    InChIKey  — (present in some datasets)

Stores raw dataset records in mol_raw.tdc_admet (migration 089_entity_linking_gaps.sql).
"""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known TDC ADMET dataset URLs
# ---------------------------------------------------------------------------
# TDC hosts benchmark datasets as tab-separated files on GitHub.
# Each file has columns: Drug_ID, Drug (SMILES), Y [, InChIKey].
# ---------------------------------------------------------------------------
ADMET_DATASETS: Dict[str, str] = {
    "Caco2_Wang": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/Caco2_Wang.tab",
    "HIA_Hou": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/HIA_Hou.tab",
    "Pgp_Broccatelli": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/Pgp_Broccatelli.tab",
    "Bioavailability_Ma": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/Bioavailability_Ma.tab",
    "Lipophilicity_AstraZeneca": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/Lipophilicity_AstraZeneca.tab",
    "Aqueous_Solubility_Delaney": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/Aqueous_Solubility_Delaney.tab",
    "BBB_Martini": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/BBB_Martini.tab",
    "PPBR_AZ": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/PPBR_AZ.tab",
    "VDss_Lombardo": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/VDss_Lombardo.tab",
    "CYP2C19_Veith": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/CYP2C19_Veith.tab",
    "CYP2D6_Veith": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/CYP2D6_Veith.tab",
    "CYP3A4_Veith": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/CYP3A4_Veith.tab",
    "Half_Life_Obach": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/Half_Life_Obach.tab",
    "Clearance_Hepatocyte_AZ": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/Clearance_Hepatocyte_AZ.tab",
    "hERG": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/hERG.tab",
    "hERG_Karim": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/hERG_Karim.tab",
    "AMES": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/AMES.tab",
    "DILI": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/DILI.tab",
    "LD50_Zhu": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/LD50_Zhu.tab",
    "ClinTox": "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/ClinTox.tab",
}

SOURCE_NAME = "tdc_admet"
BASE_RESOURCE_URL = "https://raw.githubusercontent.com/mims-harvard/TDC/main/tdc/resource/"

DEFAULT_MAX_ROWS_PER_DATASET = 5000


class TDCAdmetFetcher(BaseFetcher):
    """Fetcher for TDC ADMET benchmark datasets.

    Downloads TSV files from the mims-harvard/TDC GitHub repository and
    parses each into a list of compound-endpoint records.

    Each fetched dataset is returned as one record in the result:
        {
            "dataset_name": "Caco2_Wang",
            "data": [
                {"Drug_ID": "...", "Drug": "<SMILES>", "Y": "...", ...},
                ...
            ]
        }
    """

    SOURCE_NAME = SOURCE_NAME
    BASE_URL = BASE_RESOURCE_URL

    def get_latest_url(self) -> str:
        return BASE_RESOURCE_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download and parse TDC ADMET datasets.

        Keyword Args:
            datasets: List of dataset names to fetch (default: all in ADMET_DATASETS).
            max_rows_per_dataset: Maximum rows to include per dataset (default: 5000).

        Returns:
            Dict with:
                status: "success" | "partial" | "failed"
                records: list of dicts, each with "dataset_name" and "data" keys
                record_count: total individual compound rows across all datasets
                hash: MD5 of all dataset names returned
                datasets_fetched: count of successfully downloaded datasets
                datasets_skipped: count of datasets that could not be downloaded
        """
        requested_datasets: Optional[List[str]] = kwargs.get("datasets", None)
        max_rows: int = kwargs.get("max_rows_per_dataset", DEFAULT_MAX_ROWS_PER_DATASET)

        if requested_datasets is not None:
            # Filter to only known datasets; warn about unknowns
            unknown = [d for d in requested_datasets if d not in ADMET_DATASETS]
            if unknown:
                logger.warning(
                    "TDC ADMET: requested unknown datasets (will skip): %s", unknown
                )
            target_datasets = {
                k: v for k, v in ADMET_DATASETS.items() if k in requested_datasets
            }
        else:
            target_datasets = ADMET_DATASETS

        records: List[Dict[str, Any]] = []
        datasets_fetched = 0
        datasets_skipped = 0
        total_rows = 0

        for dataset_name, url in target_datasets.items():
            try:
                rows = self._fetch_dataset(dataset_name, url, max_rows)
                records.append({
                    "dataset_name": dataset_name,
                    "data": rows,
                })
                datasets_fetched += 1
                total_rows += len(rows)
                logger.info(
                    "TDC ADMET: fetched dataset '%s' — %d rows", dataset_name, len(rows)
                )
            except Exception as exc:
                datasets_skipped += 1
                logger.warning(
                    "TDC ADMET: skipping dataset '%s' (fetch failed): %s",
                    dataset_name,
                    exc,
                )

        content_hash = hashlib.md5(
            json.dumps(
                sorted(r["dataset_name"] for r in records),
                sort_keys=True,
            ).encode()
        ).hexdigest()

        status = "success" if datasets_skipped == 0 else ("partial" if datasets_fetched > 0 else "failed")

        result: Dict[str, Any] = {
            "status": status,
            "records": records,
            "record_count": total_rows,
            "hash": content_hash,
            "datasets_fetched": datasets_fetched,
            "datasets_skipped": datasets_skipped,
        }
        self.log_fetch_result({"status": status, "records": datasets_fetched})
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_dataset(
        self, dataset_name: str, url: str, max_rows: int
    ) -> List[Dict[str, Any]]:
        """Download and parse a single TDC TSV dataset.

        Args:
            dataset_name: Logical name of the dataset (for logging).
            url: Direct URL to the .tab (TSV) file.
            max_rows: Maximum number of rows to return.

        Returns:
            List of row dicts (keys: Drug_ID, Drug, Y, and optionally InChIKey).

        Raises:
            requests.HTTPError: If the download fails (e.g. 404).
            ValueError: If the TSV cannot be parsed.
        """
        response = self.session.get(url, timeout=60)
        response.raise_for_status()

        content = response.text
        rows = self._parse_tsv(content, max_rows)
        return rows

    def _parse_tsv(self, content: str, max_rows: int) -> List[Dict[str, Any]]:
        """Parse TSV content into a list of row dicts.

        Handles both tab-delimited and edge cases where the file uses
        a single header line followed by data rows.  Only known ADMET
        columns (Drug_ID, Drug, Y, InChIKey) are kept; extra columns are
        preserved as-is.

        Args:
            content: Raw TSV text from the TDC GitHub file.
            max_rows: Maximum rows to return (excluding header).

        Returns:
            List of dicts, one per data row.
        """
        lines = content.splitlines()
        if not lines:
            return []

        # Detect delimiter — TDC files use tab
        header_line = lines[0]
        delimiter = "\t" if "\t" in header_line else ","

        headers = [h.strip() for h in header_line.split(delimiter)]

        rows: List[Dict[str, Any]] = []
        for line in lines[1:]:
            if not line.strip():
                continue
            if len(rows) >= max_rows:
                break

            parts = line.split(delimiter)
            # Pad short rows to match header length
            while len(parts) < len(headers):
                parts.append("")

            row = {headers[i]: parts[i].strip() for i in range(len(headers))}

            # Normalize the Y column: try numeric conversion, keep as string if not
            if "Y" in row:
                try:
                    row["Y"] = float(row["Y"])
                except (ValueError, TypeError):
                    pass  # leave as string for binary labels like "0"/"1"

            rows.append(row)

        return rows
