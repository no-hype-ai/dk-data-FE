"""Health Canada Drug Product Database (DPD) fetcher — bulk ZIP of TXT files.

Downloads the DPD extract files from Health Canada. The extracts page provides
ZIP archives containing pipe-delimited TXT files covering drug products,
active ingredients, companies, dosage forms, packaging, etc.

Primary URL:
  https://www.canada.ca/en/health-canada/services/drugs-health-products/
  drug-products/drug-product-database/extracts.html

The all-files ZIP URL (allfiles.zip) bundles every extract:
  https://open.canada.ca/data/dataset/.../download/allfiles.zip (Open Government Portal)

Each TXT file is pipe-delimited (|) with a header row.
All files are concatenated into a single record list, tagged with their
source filename so the loader can differentiate.

Stores one JSONB record per row in mol_raw.health_canada_dpd.

Uses extractall with path filter (C.4 zip fix pattern) to avoid
zip-slip vulnerabilities.
"""

import csv
import hashlib
import io
import logging
import os
import zipfile
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

_ALLFILES_URL = (
    "https://open.canada.ca/data/dataset/bf55e42a-63cb-4556-bfd8-44f26e5a36fe/"
    "resource/b05ae610-0366-478f-993f-b4afbdaadbc6/download/allfiles.zip"
)

# Expected TXT files inside the ZIP and their human-readable labels
_EXPECTED_FILES = {
    "drug.txt": "drug_product",
    "form.txt": "dosage_form",
    "route.txt": "route_of_administration",
    "status.txt": "product_status",
    "ingred.txt": "active_ingredient",
    "ther.txt": "therapeutic_class",
    "comp.txt": "company",
    "package.txt": "packaging",
    "pharm.txt": "pharmaceutical_standard",
    "schedule.txt": "schedule",
    "biosimilar.txt": "biosimilar",
    "vet.txt": "veterinary_species",
}


class HealthCanadaDPDFetcher(BaseFetcher):
    """Fetcher for Health Canada Drug Product Database via bulk ZIP extract."""

    SOURCE_NAME = "health_canada_dpd"
    BASE_URL = "https://health-products.canada.ca"

    def get_latest_url(self) -> str:
        return _ALLFILES_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Download the Health Canada DPD allfiles ZIP and parse all TXT files.

        Returns:
            Dict with keys: status, records, record_count, hash, error.
        """
        max_records: Optional[int] = kwargs.get("max_records")

        try:
            logger.info("Health Canada DPD: downloading allfiles ZIP from %s", _ALLFILES_URL)
            resp = self.session.get(_ALLFILES_URL, timeout=300, stream=True)
            resp.raise_for_status()

            content = resp.content
            content_hash = hashlib.sha256(content).hexdigest()

            records = self._extract_and_parse(content, max_records)

            logger.info("Health Canada DPD: parsed %d total rows across all files", len(records))

            if not records:
                msg = "Health Canada DPD: parsed 0 rows — treating as source_unavailable"
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
            logger.exception("Health Canada DPD fetch failed: %s", exc)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(exc),
            }
            self.log_fetch_result(result)
            return result

    def _extract_and_parse(
        self, content: bytes, max_records: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Extract ZIP and parse all pipe-delimited TXT files.

        Uses extractall with a safe path filter (C.4 zip fix) to avoid
        zip-slip directory traversal attacks.
        """
        records: List[Dict[str, Any]] = []

        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for member in zf.namelist():
                # C.4 zip fix: reject paths with directory traversal
                basename = os.path.basename(member)
                if not basename or basename != member.replace("\\", "/").split("/")[-1]:
                    logger.warning("DPD: skipping suspicious ZIP member: %s", member)
                    continue

                lower_name = basename.lower()
                if not lower_name.endswith(".txt"):
                    continue

                file_label = _EXPECTED_FILES.get(lower_name, lower_name.replace(".txt", ""))

                logger.debug("DPD: parsing %s (label=%s)", basename, file_label)
                with zf.open(member) as f:
                    file_records = self._parse_pipe_delimited(f, file_label)
                    records.extend(file_records)

                if max_records and len(records) >= max_records:
                    records = records[:max_records]
                    break

        return records

    @staticmethod
    def _parse_pipe_delimited(
        file_obj, file_label: str
    ) -> List[Dict[str, Any]]:
        """Parse a pipe-delimited TXT file into row dicts.

        Column names are normalised to lowercase with underscores.
        Each record is tagged with _dpd_file to identify the source file.
        """
        text = file_obj.read().decode("latin-1", errors="replace")
        reader = csv.DictReader(io.StringIO(text), delimiter="|")
        records: List[Dict[str, Any]] = []
        for row in reader:
            record = {
                k.strip().lower().replace(" ", "_"): (v.strip() if v else None)
                for k, v in row.items()
                if k is not None
            }
            record["_dpd_file"] = file_label
            # Skip entirely blank rows (ignoring the tag)
            if all(v is None for k, v in record.items() if k != "_dpd_file"):
                continue
            records.append(record)
        return records
