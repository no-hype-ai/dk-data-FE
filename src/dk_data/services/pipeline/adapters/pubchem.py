"""MCP Adapter: pubchem

Feature: 015-assessment-dashboard-integration

Uses PubChem PUG REST substance endpoint which covers both small molecules
and biologics (compound endpoint returns 404 for mAbs like durvalumab).
"""
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "pubchem"

    @property
    def raw_table(self) -> str:
        return "pubchem"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """PubChem PUG REST substance name lookup.

        Uses /substance/name/{name}/JSON rather than /compound/name/{name}/JSON
        because compound DB only has small molecules; biologics (mAbs, proteins)
        are only in the substance DB. The substance endpoint returns data for both.
        """
        return f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/substance/name/{quote(drug_name)}/JSON"

    def normalize(self, api_response: dict) -> dict:
        return api_response
