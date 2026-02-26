"""MCP Adapter: drugbank
Feature: 015-assessment-dashboard-integration

Uses a local DrugBank XML dump instead of the paid API.
Set DRUGBANK_XML_PATH env var to point at the extracted XML file.
Falls back gracefully if not available.
"""
import os
import xml.etree.ElementTree as ET
from functools import lru_cache
from typing import Dict, Optional
from urllib.parse import quote

from loguru import logger

from .base import BaseAdapter

# DrugBank XML namespace
_NS = {"db": "http://www.drugbank.ca"}

# In-memory index: lowercased drug name → XML Element offset
_DRUG_INDEX: Optional[Dict[str, dict]] = None


def _get_xml_path() -> Optional[str]:
    """Resolve the DrugBank XML file path."""
    path = os.environ.get("DRUGBANK_XML_PATH")
    if path and os.path.isfile(path):
        return path
    # Common locations
    for candidate in [
        "/app/data/drugbank_all_full_database.xml",
        os.path.expanduser("~/Downloads/drugbank_all_full_database.xml"),
    ]:
        if os.path.isfile(candidate):
            return candidate
    return None


def _build_index(xml_path: str) -> Dict[str, dict]:
    """Build an in-memory name→summary index using iterparse (memory efficient).

    Only parses top-level <drug> elements and extracts key fields.
    """
    logger.info(f"Building DrugBank index from {xml_path} (this may take 30-60s)...")
    index: Dict[str, dict] = {}
    context = ET.iterparse(xml_path, events=("end",))

    for event, elem in context:
        if elem.tag == f"{{{_NS['db']}}}drug" and elem.get("type"):
            drugbank_id_el = elem.find("db:drugbank-id[@primary='true']", _NS)
            name_el = elem.find("db:name", _NS)
            desc_el = elem.find("db:description", _NS)
            cas_el = elem.find("db:cas-number", _NS)
            state_el = elem.find("db:state", _NS)
            indication_el = elem.find("db:indication", _NS)
            pharmacodynamics_el = elem.find("db:pharmacodynamics", _NS)
            mechanism_el = elem.find("db:mechanism-of-action", _NS)
            absorption_el = elem.find("db:absorption", _NS)
            half_life_el = elem.find("db:half-life", _NS)

            groups = [g.text for g in elem.findall("db:groups/db:group", _NS) if g.text]
            categories = [
                c.find("db:category", _NS).text
                for c in elem.findall("db:categories/db:category", _NS)
                if c.find("db:category", _NS) is not None and c.find("db:category", _NS).text
            ][:10]
            synonyms = [
                s.text for s in elem.findall("db:synonyms/db:synonym", _NS) if s.text
            ][:20]

            # Targets
            targets = []
            for t in elem.findall("db:targets/db:target", _NS)[:10]:
                t_name = t.find("db:name", _NS)
                t_actions = [a.text for a in t.findall("db:actions/db:action", _NS) if a.text]
                if t_name is not None and t_name.text:
                    targets.append({"name": t_name.text, "actions": t_actions})

            name = name_el.text if name_el is not None else None
            if not name:
                elem.clear()
                continue

            entry = {
                "drugbank_id": drugbank_id_el.text if drugbank_id_el is not None else None,
                "name": name,
                "description": (desc_el.text or "")[:2000] if desc_el is not None else None,
                "cas_number": cas_el.text if cas_el is not None else None,
                "state": state_el.text if state_el is not None else None,
                "type": elem.get("type"),
                "groups": groups,
                "categories": categories,
                "synonyms": synonyms,
                "indication": (indication_el.text or "")[:2000] if indication_el is not None else None,
                "pharmacodynamics": (pharmacodynamics_el.text or "")[:1000] if pharmacodynamics_el is not None else None,
                "mechanism_of_action": (mechanism_el.text or "")[:1000] if mechanism_el is not None else None,
                "absorption": (absorption_el.text or "")[:500] if absorption_el is not None else None,
                "half_life": half_life_el.text if half_life_el is not None else None,
                "targets": targets,
            }

            # Index by name and all synonyms
            index[name.lower()] = entry
            for syn in synonyms:
                index[syn.lower()] = entry

            elem.clear()

    logger.info(f"DrugBank index built: {len(index)} entries")
    return index


def get_drug_index() -> Optional[Dict[str, dict]]:
    """Get or build the DrugBank index."""
    global _DRUG_INDEX
    if _DRUG_INDEX is not None:
        return _DRUG_INDEX

    xml_path = _get_xml_path()
    if not xml_path:
        logger.warning("DrugBank XML not found. Set DRUGBANK_XML_PATH or place at ~/Downloads/drugbank_all_full_database.xml")
        return None

    _DRUG_INDEX = _build_index(xml_path)
    return _DRUG_INDEX


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "drugbank"

    @property
    def raw_table(self) -> str:
        return "drugbank"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """Not used for local XML lookup — kept for interface compliance."""
        return f"{base_url}?q={quote(drug_name)}"

    def normalize(self, api_response: dict) -> dict:
        """Normalize DrugBank response."""
        return api_response
