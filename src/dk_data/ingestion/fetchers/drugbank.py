"""DrugBank Data Fetcher.

Feature: 011-datasource-integration
Task: Phase 6 / US4 — credential-gated source (DrugBank)

Fetches drug entries from the DrugBank XML download, which requires
an API key for authentication. Monthly refresh cadence.

Source: https://go.drugbank.com/releases/latest
"""

import hashlib
import logging
import os
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# DrugBank XML namespace
DRUGBANK_NS = "{http://www.drugbank.ca}"


class DrugBankFetcher(BaseFetcher):
    """Fetcher for DrugBank drug database (credential-gated)."""

    SOURCE_NAME = "drugbank"
    BASE_URL = "https://go.drugbank.com"

    # DrugBank download URL for the full XML dataset
    DOWNLOAD_URL = "https://go.drugbank.com/releases/latest/downloads/all-full-database"

    # Maximum number of drug entries to process (safety limit)
    MAX_ENTRIES = 50_000

    # Default local ZIP path relative to project root
    DEFAULT_LOCAL_ZIP = "data/drugbank/drugbank_all_full_database.xml.zip"

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the DrugBank fetcher.

        Reads DRUGBANK_API_KEY from the environment.

        Args:
            data_dir: Directory to store downloaded files.
        """
        super().__init__(data_dir)
        self.api_key: Optional[str] = os.environ.get("DRUGBANK_API_KEY")

        # Resolve project root (walk up from this file to find the repo root)
        self._project_root = Path(__file__).resolve().parents[4]  # src/dk_data/ingestion/fetchers -> root

        if self.api_key:
            logger.info("DrugBank API key detected")
        else:
            logger.info(
                "No DRUGBANK_API_KEY set; will attempt local file before API download"
            )

    def get_latest_url(self) -> str:
        """Get the DrugBank download URL."""
        return self.DOWNLOAD_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch drug entries from the DrugBank XML download.

        Supports loading from a local ZIP file to avoid needing API credentials.
        Resolution order for the XML source:
          1. ``file_path`` kwarg or ``self.params["file_path"]``
          2. Default local ZIP at ``data/drugbank/drugbank_all_full_database.xml.zip``
          3. API download (requires DRUGBANK_API_KEY)

        Keyword Args:
            max_entries: Maximum drug entries to process (default: 50000).
            file_path: Explicit path to a local DrugBank XML or ZIP file.

        Returns:
            Dictionary with:
                - status: 'success' or 'failed'
                - records: list of drug record dicts
                - record_count: number of records fetched
                - hash: SHA-256 hash of the content
                - error: error message (if failed)
        """
        max_entries = kwargs.get("max_entries", self.MAX_ENTRIES)

        try:
            # Resolve local file path
            local_file = self._resolve_local_file(kwargs.get("file_path"))

            if local_file:
                logger.info("Using local DrugBank file: %s", local_file)
                filepath = self._extract_xml_from_zip(local_file)
            else:
                # Fall back to API download
                if not self.api_key:
                    raise ValueError(
                        "No local DrugBank file found and DRUGBANK_API_KEY "
                        "environment variable is not set. Provide a local file "
                        "via file_path or set the API key."
                    )

                logger.info("Fetching DrugBank XML database via API")
                filepath = self._download_drugbank_xml()

            # Parse the XML file
            records = self._parse_drugbank_xml(filepath, max_entries=max_entries)

            # Compute content hash
            content_hash = hashlib.sha256(
                str(sorted(r["drugbank_id"] for r in records)).encode()
            ).hexdigest()

            result = {
                "status": "success",
                "records": records,
                "record_count": len(records),
                "hash": content_hash,
            }

            logger.info("DrugBank fetch complete: %d records", len(records))
            self.log_fetch_result({"status": "success", "records": len(records)})
            return result

        except Exception as e:
            logger.exception("Failed to fetch DrugBank data: %s", e)
            result = {
                "status": "failed",
                "records": [],
                "record_count": 0,
                "hash": None,
                "error": str(e),
            }
            self.log_fetch_result(result)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_local_file(self, file_path_kwarg: Optional[str] = None) -> Optional[Path]:
        """Resolve a local DrugBank file, checking multiple sources.

        Resolution order:
          1. Explicit ``file_path`` kwarg
          2. ``self.params["file_path"]``
          3. Default local ZIP relative to project root

        Returns:
            Path to the local file if found, else None.
        """
        candidates = [
            file_path_kwarg,
            self.params.get("file_path"),
        ]

        for candidate in candidates:
            if candidate:
                p = Path(candidate)
                if p.is_file():
                    return p
                logger.warning("Specified file_path does not exist: %s", candidate)

        # Check default location relative to project root
        default_path = self._project_root / self.DEFAULT_LOCAL_ZIP
        if default_path.is_file():
            return default_path

        return None

    def _extract_xml_from_zip(self, zip_path: Path) -> str:
        """Extract the XML file from a DrugBank ZIP archive.

        Args:
            zip_path: Path to the ZIP file.

        Returns:
            Path to the extracted XML file.
        """
        if not zipfile.is_zipfile(zip_path):
            # Not a ZIP — assume it's already a plain XML file
            logger.info("File is not a ZIP; treating as plain XML: %s", zip_path)
            return str(zip_path)

        extract_dir = self.data_dir / "drugbank_extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            # Find the XML file inside the archive
            xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not xml_names:
                raise ValueError(
                    f"No XML file found inside ZIP archive: {zip_path}"
                )

            xml_name = xml_names[0]
            logger.info(
                "Extracting '%s' from %s (%.2f MB compressed)",
                xml_name,
                zip_path.name,
                zip_path.stat().st_size / 1024 / 1024,
            )
            zf.extract(xml_name, extract_dir)

        extracted_path = extract_dir / xml_name
        logger.info(
            "Extracted DrugBank XML: %s (%.2f MB)",
            extracted_path,
            extracted_path.stat().st_size / 1024 / 1024,
        )
        return str(extracted_path)

    def _download_drugbank_xml(self) -> str:
        """Download the DrugBank XML file with authentication.

        Returns:
            Path to the downloaded XML file.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/xml",
        }

        filepath = self.data_dir / "drugbank_full.xml"

        logger.info("Downloading DrugBank XML to %s", filepath)
        response = self.session.get(
            self.get_latest_url(),
            headers=headers,
            stream=True,
            timeout=600,
        )
        response.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = filepath.stat().st_size / 1024 / 1024
        logger.info("Downloaded DrugBank XML: %.2f MB", size_mb)
        return str(filepath)

    def _parse_drugbank_xml(
        self,
        filepath: str,
        max_entries: int = 50_000,
    ) -> List[Dict[str, Any]]:
        """Parse drug entries from DrugBank XML.

        Uses iterparse for memory-efficient processing of large XML files.

        Args:
            filepath: Path to the DrugBank XML file.
            max_entries: Maximum entries to process.

        Returns:
            List of normalized drug record dicts.
        """
        records: List[Dict[str, Any]] = []

        logger.info("Parsing DrugBank XML from %s", filepath)

        try:
            for event, elem in ET.iterparse(filepath, events=("end",)):
                if elem.tag == f"{DRUGBANK_NS}drug" or elem.tag == "drug":
                    record = self._parse_drug_entry(elem)
                    if record:
                        records.append(record)

                    # Free memory
                    elem.clear()

                    if len(records) >= max_entries:
                        logger.info(
                            "Reached max_entries limit (%d), stopping parse",
                            max_entries,
                        )
                        break

        except ET.ParseError as e:
            logger.error("XML parse error: %s", e)

        logger.info("Parsed %d drug entries from DrugBank XML", len(records))
        return records

    def _parse_drug_entry(self, elem: ET.Element) -> Optional[Dict[str, Any]]:
        """Parse a single <drug> element into a record dict.

        Args:
            elem: XML Element for a single drug entry.

        Returns:
            Normalized record dict, or None if the entry lacks a DrugBank ID.
        """
        # Try namespaced and non-namespaced tags
        drugbank_id = self._get_drugbank_id(elem)
        if not drugbank_id:
            return None

        name = self._safe_text(elem, f"{DRUGBANK_NS}name") or self._safe_text(elem, "name")
        description = (
            self._safe_text(elem, f"{DRUGBANK_NS}description")
            or self._safe_text(elem, "description")
        )
        cas_number = (
            self._safe_text(elem, f"{DRUGBANK_NS}cas-number")
            or self._safe_text(elem, "cas-number")
        )
        indication = (
            self._safe_text(elem, f"{DRUGBANK_NS}indication")
            or self._safe_text(elem, "indication")
        )
        pharmacodynamics = (
            self._safe_text(elem, f"{DRUGBANK_NS}pharmacodynamics")
            or self._safe_text(elem, "pharmacodynamics")
        )

        # Parse categories
        categories = self._parse_categories(elem)

        # Parse targets
        targets = self._parse_bio_entities(elem, "targets", "target")

        # Parse enzymes
        enzymes = self._parse_bio_entities(elem, "enzymes", "enzyme")

        return {
            "drugbank_id": drugbank_id,
            "name": name,
            "description": description,
            "cas_number": cas_number,
            "categories": categories if categories else None,
            "targets": targets if targets else None,
            "enzymes": enzymes if enzymes else None,
            "indication": indication,
            "pharmacodynamics": pharmacodynamics,
        }

    def _get_drugbank_id(self, elem: ET.Element) -> Optional[str]:
        """Extract the primary DrugBank ID from a drug element.

        DrugBank IDs are stored in <drugbank-id> elements; the primary
        one has primary='true' attribute.
        """
        # Try namespaced
        for id_elem in elem.findall(f"{DRUGBANK_NS}drugbank-id"):
            if id_elem.get("primary") == "true" and id_elem.text:
                return id_elem.text.strip()

        # Try non-namespaced
        for id_elem in elem.findall("drugbank-id"):
            if id_elem.get("primary") == "true" and id_elem.text:
                return id_elem.text.strip()

        # Fallback: first drugbank-id element
        id_elem = elem.find(f"{DRUGBANK_NS}drugbank-id")
        if id_elem is None:
            id_elem = elem.find("drugbank-id")
        if id_elem is not None and id_elem.text:
            return id_elem.text.strip()

        return None

    def _parse_categories(self, elem: ET.Element) -> List[str]:
        """Extract drug categories from a drug element."""
        categories: List[str] = []

        # Try namespaced path
        cats_elem = elem.find(f"{DRUGBANK_NS}categories")
        if cats_elem is None:
            cats_elem = elem.find("categories")

        if cats_elem is not None:
            for cat in cats_elem:
                cat_name = (
                    self._safe_text(cat, f"{DRUGBANK_NS}category")
                    or self._safe_text(cat, "category")
                )
                if cat_name:
                    categories.append(cat_name)

        return categories

    def _parse_bio_entities(
        self,
        elem: ET.Element,
        container_tag: str,
        item_tag: str,
    ) -> List[Dict[str, Any]]:
        """Parse biological entity lists (targets, enzymes, etc.).

        Args:
            elem: Parent drug element.
            container_tag: Container element tag (e.g. 'targets').
            item_tag: Individual item tag (e.g. 'target').

        Returns:
            List of entity dicts with id, name, and actions.
        """
        entities: List[Dict[str, Any]] = []

        container = elem.find(f"{DRUGBANK_NS}{container_tag}")
        if container is None:
            container = elem.find(container_tag)

        if container is None:
            return entities

        for item in container:
            entity_id = (
                self._safe_text(item, f"{DRUGBANK_NS}id")
                or self._safe_text(item, "id")
            )
            entity_name = (
                self._safe_text(item, f"{DRUGBANK_NS}name")
                or self._safe_text(item, "name")
            )

            # Parse actions
            actions: List[str] = []
            actions_elem = item.find(f"{DRUGBANK_NS}actions")
            if actions_elem is None:
                actions_elem = item.find("actions")
            if actions_elem is not None:
                for action in actions_elem:
                    if action.text:
                        actions.append(action.text.strip())

            if entity_name:
                entities.append({
                    "id": entity_id,
                    "name": entity_name,
                    "actions": actions,
                })

        return entities

    @staticmethod
    def _safe_text(parent: Optional[ET.Element], path: str) -> Optional[str]:
        """Safely extract text from an XML sub-element."""
        if parent is None:
            return None
        elem = parent.find(path)
        if elem is not None and elem.text:
            return elem.text.strip()
        return None
