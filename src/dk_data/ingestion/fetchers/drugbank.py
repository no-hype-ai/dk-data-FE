"""DrugBank Data Fetcher.

Feature: 011-datasource-integration
Task: Phase 6 / US4 — credential-gated source (DrugBank)

Fetches drug entries from the DrugBank XML download, which requires
an API key for authentication. Monthly refresh cadence.

Source: https://go.drugbank.com/releases/latest
"""

import hashlib
import io
import logging
import os
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseFetcher

# Default local file locations (repo-relative then container path)
_REPO_DATA_DIR = Path(__file__).resolve().parents[4] / "data" / "drugbank"
_CONTAINER_DATA_DIR = Path("/app/data/drugbank")
_DEFAULT_ZIP_NAME = "drugbank_all_full_database.xml.zip"

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

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize the DrugBank fetcher.

        Reads DRUGBANK_API_KEY from the environment.

        Args:
            data_dir: Directory to store downloaded files.
        """
        super().__init__(data_dir)
        self.api_key: Optional[str] = os.environ.get("DRUGBANK_API_KEY")
        if self.api_key:
            logger.info("DrugBank API key detected")
        else:
            logger.warning(
                "No DRUGBANK_API_KEY set; DrugBank fetch will fail without authentication"
            )

    def get_latest_url(self) -> str:
        """Get the DrugBank download URL."""
        return self.DOWNLOAD_URL

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch drug entries from the DrugBank XML download.

        Keyword Args:
            max_entries: Maximum drug entries to process (default: 50000).

        Returns:
            Dictionary with:
                - status: 'success' or 'failed'
                - records: list of drug record dicts
                - record_count: number of records fetched
                - hash: SHA-256 hash of the content
                - error: error message (if failed)
        """
        max_entries = kwargs.get("max_entries") or self.params.get("max_entries") or self.MAX_ENTRIES

        try:
            local_zip = self._find_local_zip()
            if local_zip:
                logger.info("Using local DrugBank ZIP: %s", local_zip)
                filepath = self._extract_xml_from_zip(local_zip)
            elif self.api_key:
                logger.info("Fetching DrugBank XML database from remote")
                filepath = self._download_drugbank_xml()
            else:
                msg = (
                    f"No local DrugBank ZIP found in {_REPO_DATA_DIR} or {_CONTAINER_DATA_DIR} "
                    "and DRUGBANK_API_KEY is not set. "
                    f"Download from https://go.drugbank.com/releases/latest and place at "
                    f"{_REPO_DATA_DIR / _DEFAULT_ZIP_NAME}"
                )
                logger.warning(msg)
                result = {
                    "status": "source_unavailable",
                    "records": [],
                    "record_count": 0,
                    "hash": None,
                    "error": msg,
                }
                self.log_fetch_result(result)
                return result

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

    def _find_local_zip(self) -> Optional[Path]:
        """Return path to a local DrugBank ZIP if one exists, else None."""
        custom = self.params.get("local_file")
        if custom:
            p = Path(custom)
            return p if p.exists() else None
        for data_dir in (_CONTAINER_DATA_DIR, _REPO_DATA_DIR):
            candidate = data_dir / _DEFAULT_ZIP_NAME
            if candidate.exists():
                return candidate
        return None

    def _extract_xml_from_zip(self, zip_path: Path) -> str:
        """Extract the XML from a DrugBank ZIP to a temp file. Returns path."""
        tmp = tempfile.NamedTemporaryFile(
            mode="wb", suffix=".xml", delete=False, prefix="drugbank_"
        )
        with zipfile.ZipFile(zip_path) as zf:
            # The ZIP contains exactly one file: 'full database.xml'
            xml_name = next(n for n in zf.namelist() if n.endswith(".xml"))
            with zf.open(xml_name) as src:
                for chunk in iter(lambda: src.read(8192), b""):
                    tmp.write(chunk)
        tmp.close()
        logger.info("Extracted DrugBank XML to %s", tmp.name)
        return tmp.name

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

        # Drug state (solid, liquid, gas)
        state = self._safe_text(elem, f"{DRUGBANK_NS}state") or self._safe_text(elem, "state")

        # Parse groups (approved, investigational, withdrawn, etc.)
        groups = self._parse_groups(elem)

        # Parse categories
        categories = self._parse_categories(elem)

        # Parse classification (kingdom/superclass/class/subclass hierarchy)
        classification = self._parse_classification(elem)

        # Parse targets
        targets = self._parse_bio_entities(elem, "targets", "target")

        # Parse enzymes
        enzymes = self._parse_bio_entities(elem, "enzymes", "enzyme")

        # Parse carriers and transporters
        carriers = self._parse_bio_entities(elem, "carriers", "carrier")
        transporters = self._parse_bio_entities(elem, "transporters", "transporter")

        # Parse calculated properties (InChI, InChIKey, SMILES, molecular formula, etc.)
        calc_props = self._parse_calculated_properties(elem)

        # Parse experimental properties
        exp_props = self._parse_experimental_properties(elem)

        # Parse ATC codes
        atc_codes = self._parse_atc_codes(elem)

        # Parse pathways
        pathways = self._parse_pathways(elem)

        # Parse drug interactions
        drug_interactions = self._parse_drug_interactions(elem)

        # Parse external identifiers (ChEMBL, PubChem, etc.)
        external_ids = self._parse_external_identifiers(elem)

        # Parse synonyms
        synonyms = self._parse_synonyms(elem)

        # Additional text fields
        mechanism_of_action = (
            self._safe_text(elem, f"{DRUGBANK_NS}mechanism-of-action")
            or self._safe_text(elem, "mechanism-of-action")
        )
        absorption = (
            self._safe_text(elem, f"{DRUGBANK_NS}absorption")
            or self._safe_text(elem, "absorption")
        )
        protein_binding = (
            self._safe_text(elem, f"{DRUGBANK_NS}protein-binding")
            or self._safe_text(elem, "protein-binding")
        )
        metabolism = (
            self._safe_text(elem, f"{DRUGBANK_NS}metabolism")
            or self._safe_text(elem, "metabolism")
        )
        half_life = (
            self._safe_text(elem, f"{DRUGBANK_NS}half-life")
            or self._safe_text(elem, "half-life")
        )
        route_of_elimination = (
            self._safe_text(elem, f"{DRUGBANK_NS}route-of-elimination")
            or self._safe_text(elem, "route-of-elimination")
        )
        clearance = (
            self._safe_text(elem, f"{DRUGBANK_NS}clearance")
            or self._safe_text(elem, "clearance")
        )
        volume_of_distribution = (
            self._safe_text(elem, f"{DRUGBANK_NS}volume-of-distribution")
            or self._safe_text(elem, "volume-of-distribution")
        )
        toxicity = (
            self._safe_text(elem, f"{DRUGBANK_NS}toxicity")
            or self._safe_text(elem, "toxicity")
        )
        drug_type = elem.get("type")

        # Parse food interactions
        food_interactions = self._parse_food_interactions(elem)

        # Parse patents
        patents = self._parse_patents(elem)

        # Parse international brands
        international_brands = self._parse_international_brands(elem)

        # Derive monoisotopic_mass from experimental properties
        monoisotopic_mass_str = exp_props.get("monoisotopic_weight") or exp_props.get("monoisotopic_mass")

        # Derive UNII from external_identifiers
        unii = external_ids.get("fda_unii_code") or external_ids.get("unii")

        return {
            "drugbank_id": drugbank_id,
            "name": name,
            "description": description,
            "cas_number": cas_number,
            "drug_type": drug_type,
            "state": state,
            "groups": groups if groups else None,
            "categories": categories if categories else None,
            "targets": targets if targets else None,
            "enzymes": enzymes if enzymes else None,
            "carriers": carriers if carriers else None,
            "transporters": transporters if transporters else None,
            "indication": indication,
            "pharmacodynamics": pharmacodynamics,
            "mechanism_of_action": mechanism_of_action,
            "absorption": absorption,
            "protein_binding": protein_binding,
            "metabolism": metabolism,
            "half_life": half_life,
            "route_of_elimination": route_of_elimination,
            "clearance": clearance,
            "volume_of_distribution": volume_of_distribution,
            "toxicity": toxicity,
            "atc_codes": atc_codes if atc_codes else None,
            "pathways": pathways if pathways else None,
            "drug_interactions": drug_interactions if drug_interactions else None,
            "food_interactions": food_interactions if food_interactions else None,
            "synonyms": synonyms if synonyms else None,
            "external_identifiers": external_ids if external_ids else None,
            "patents": patents if patents else None,
            "international_brands": international_brands if international_brands else None,
            "monoisotopic_mass": monoisotopic_mass_str,
            "unii": unii,
            # Calculated properties (structural identifiers)
            "smiles": calc_props.get("smiles") or calc_props.get("SMILES"),
            "inchi": calc_props.get("inchi") or calc_props.get("InChI"),
            "inchi_key": calc_props.get("inchi_key") or calc_props.get("InChIKey"),
            "molecular_formula": calc_props.get("molecular_formula") or exp_props.get("molecular_formula"),
            "molecular_weight": calc_props.get("molecular_weight") or exp_props.get("molecular_weight"),
            "calculated_properties": calc_props if calc_props else None,
            "experimental_properties": exp_props if exp_props else None,
            "classification": classification,
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

    def _parse_classification(self, elem: ET.Element) -> Optional[Dict[str, Any]]:
        """Extract drug classification from a drug element.

        DrugBank <classification> has: description, direct-parent, kingdom,
        superclass, class, subclass, alternative-parent (multiple),
        substituent (multiple).
        """
        cls_elem = elem.find(f"{DRUGBANK_NS}classification") or elem.find("classification")
        if cls_elem is None:
            return None

        result: Dict[str, Any] = {}
        for tag in ("description", "direct-parent", "kingdom", "superclass", "class", "subclass"):
            val = self._safe_text(cls_elem, f"{DRUGBANK_NS}{tag}") or self._safe_text(cls_elem, tag)
            if val:
                result[tag.replace("-", "_")] = val

        alt_parents = [
            e.text.strip()
            for e in list(cls_elem.findall(f"{DRUGBANK_NS}alternative-parent"))
            + list(cls_elem.findall("alternative-parent"))
            if e.text and e.text.strip()
        ]
        if alt_parents:
            result["alternative_parents"] = alt_parents

        substituents = [
            e.text.strip()
            for e in list(cls_elem.findall(f"{DRUGBANK_NS}substituent"))
            + list(cls_elem.findall("substituent"))
            if e.text and e.text.strip()
        ]
        if substituents:
            result["substituents"] = substituents

        return result if result else None

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

    def _parse_calculated_properties(self, elem: ET.Element) -> dict:
        """Extract calculated properties (SMILES, InChI, InChIKey, molecular weight, etc.)."""
        props = {}
        container = elem.find(f"{DRUGBANK_NS}calculated-properties") or elem.find("calculated-properties")
        if container is None:
            return props
        for prop in container:
            kind = (
                self._safe_text(prop, f"{DRUGBANK_NS}kind") or self._safe_text(prop, "kind")
            )
            value = (
                self._safe_text(prop, f"{DRUGBANK_NS}value") or self._safe_text(prop, "value")
            )
            if kind and value:
                # Normalize key names
                key = kind.lower().replace(" ", "_").replace("-", "_")
                props[key] = value
                # Also store canonical aliases
                if kind == "SMILES":
                    props["smiles"] = value
                elif kind == "InChI":
                    props["inchi"] = value
                elif kind == "InChIKey":
                    props["inchi_key"] = value
                elif kind == "Molecular Formula":
                    props["molecular_formula"] = value
                elif kind == "Molecular Weight":
                    props["molecular_weight"] = value
        return props

    def _parse_experimental_properties(self, elem: ET.Element) -> dict:
        """Extract experimental properties (molecular weight, logP, etc.)."""
        props = {}
        container = elem.find(f"{DRUGBANK_NS}experimental-properties") or elem.find("experimental-properties")
        if container is None:
            return props
        for prop in container:
            kind = (
                self._safe_text(prop, f"{DRUGBANK_NS}kind") or self._safe_text(prop, "kind")
            )
            value = (
                self._safe_text(prop, f"{DRUGBANK_NS}value") or self._safe_text(prop, "value")
            )
            if kind and value:
                key = kind.lower().replace(" ", "_").replace("-", "_")
                props[key] = value
        return props

    def _parse_atc_codes(self, elem: ET.Element) -> List[str]:
        """Extract ATC codes."""
        codes: List[str] = []
        container = elem.find(f"{DRUGBANK_NS}atc-codes") or elem.find("atc-codes")
        if container is None:
            return codes
        for atc in container:
            code = atc.get("code")
            if code:
                codes.append(code)
        return codes

    def _parse_pathways(self, elem: ET.Element) -> List[Dict[str, Any]]:
        """Extract biological pathways."""
        pathways: List[Dict[str, Any]] = []
        container = elem.find(f"{DRUGBANK_NS}pathways") or elem.find("pathways")
        if container is None:
            return pathways
        for pathway in container:
            smpdb_id = (
                self._safe_text(pathway, f"{DRUGBANK_NS}smpdb-id") or self._safe_text(pathway, "smpdb-id")
            )
            pathway_name = (
                self._safe_text(pathway, f"{DRUGBANK_NS}name") or self._safe_text(pathway, "name")
            )
            if pathway_name:
                pathways.append({"smpdb_id": smpdb_id, "name": pathway_name})
        return pathways

    def _parse_drug_interactions(self, elem: ET.Element) -> List[Dict[str, Any]]:
        """Extract drug-drug interactions."""
        interactions: List[Dict[str, Any]] = []
        container = elem.find(f"{DRUGBANK_NS}drug-interactions") or elem.find("drug-interactions")
        if container is None:
            return interactions
        for interaction in container:
            db_id = (
                self._safe_text(interaction, f"{DRUGBANK_NS}drugbank-id") or self._safe_text(interaction, "drugbank-id")
            )
            name = (
                self._safe_text(interaction, f"{DRUGBANK_NS}name") or self._safe_text(interaction, "name")
            )
            description = (
                self._safe_text(interaction, f"{DRUGBANK_NS}description") or self._safe_text(interaction, "description")
            )
            if db_id or name:
                interactions.append({"drugbank_id": db_id, "name": name, "description": description})
            if len(interactions) >= 50:  # cap to avoid huge payloads
                break
        return interactions

    def _parse_external_identifiers(self, elem: ET.Element) -> Dict[str, str]:
        """Extract external identifiers (ChEMBL ID, PubChem CID, etc.)."""
        identifiers: Dict[str, str] = {}
        container = elem.find(f"{DRUGBANK_NS}external-identifiers") or elem.find("external-identifiers")
        if container is None:
            return identifiers
        for ext_id in container:
            resource = (
                self._safe_text(ext_id, f"{DRUGBANK_NS}resource") or self._safe_text(ext_id, "resource")
            )
            identifier = (
                self._safe_text(ext_id, f"{DRUGBANK_NS}identifier") or self._safe_text(ext_id, "identifier")
            )
            if resource and identifier:
                key = resource.lower().replace(" ", "_").replace("-", "_")
                identifiers[key] = identifier
        return identifiers

    def _parse_synonyms(self, elem: ET.Element) -> List[str]:
        """Extract drug synonyms."""
        synonyms: List[str] = []
        container = elem.find(f"{DRUGBANK_NS}synonyms") or elem.find("synonyms")
        if container is None:
            return synonyms
        for synonym in container:
            text = synonym.text
            if text and text.strip():
                synonyms.append(text.strip())
        return synonyms

    def _parse_groups(self, elem: ET.Element) -> List[str]:
        """Extract drug groups (approved, investigational, withdrawn, etc.)."""
        groups: List[str] = []
        container = elem.find(f"{DRUGBANK_NS}groups") or elem.find("groups")
        if container is None:
            return groups
        for group in container:
            text = group.text
            if text and text.strip():
                groups.append(text.strip())
        return groups

    def _parse_food_interactions(self, elem: ET.Element) -> List[str]:
        """Extract food interactions."""
        interactions: List[str] = []
        container = elem.find(f"{DRUGBANK_NS}food-interactions") or elem.find("food-interactions")
        if container is None:
            return interactions
        for item in container:
            text = item.text
            if text and text.strip():
                interactions.append(text.strip())
        return interactions

    def _parse_patents(self, elem: ET.Element) -> List[Dict[str, Any]]:
        """Extract patent information."""
        patents: List[Dict[str, Any]] = []
        container = elem.find(f"{DRUGBANK_NS}patents") or elem.find("patents")
        if container is None:
            return patents
        for patent in container:
            number = (
                self._safe_text(patent, f"{DRUGBANK_NS}number") or self._safe_text(patent, "number")
            )
            country = (
                self._safe_text(patent, f"{DRUGBANK_NS}country") or self._safe_text(patent, "country")
            )
            approved = (
                self._safe_text(patent, f"{DRUGBANK_NS}approved") or self._safe_text(patent, "approved")
            )
            expires = (
                self._safe_text(patent, f"{DRUGBANK_NS}expires") or self._safe_text(patent, "expires")
            )
            pediatric_extension_elem = patent.find(f"{DRUGBANK_NS}pediatric-extension") or patent.find("pediatric-extension")
            pediatric_extension = None
            if pediatric_extension_elem is not None and pediatric_extension_elem.text:
                pediatric_extension = pediatric_extension_elem.text.strip().lower() == "true"
            if number:
                patents.append({
                    "number": number,
                    "country": country,
                    "approved": approved,
                    "expires": expires,
                    "pediatric_extension": pediatric_extension,
                })
        return patents

    def _parse_international_brands(self, elem: ET.Element) -> List[Dict[str, Any]]:
        """Extract international brand names."""
        brands: List[Dict[str, Any]] = []
        container = elem.find(f"{DRUGBANK_NS}international-brands") or elem.find("international-brands")
        if container is None:
            return brands
        for brand in container:
            brand_name = (
                self._safe_text(brand, f"{DRUGBANK_NS}name") or self._safe_text(brand, "name")
            )
            company = (
                self._safe_text(brand, f"{DRUGBANK_NS}company") or self._safe_text(brand, "company")
            )
            if brand_name:
                brands.append({"name": brand_name, "company": company})
        return brands

    @staticmethod
    def _safe_text(parent: Optional[ET.Element], path: str) -> Optional[str]:
        """Safely extract text from an XML sub-element."""
        if parent is None:
            return None
        elem = parent.find(path)
        if elem is not None and elem.text:
            return elem.text.strip()
        return None
