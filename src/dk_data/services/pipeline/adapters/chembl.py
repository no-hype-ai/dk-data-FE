"""MCP Adapter: chembl
Feature: 015-assessment-dashboard-integration
"""
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "chembl"

    @property
    def raw_table(self) -> str:
        return "chembl"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """ChEMBL REST API uses q parameter with format=json."""
        return f"{base_url}?q={quote(drug_name)}&format=json"

    def normalize(self, api_response: dict) -> dict:
        """Normalize ChEMBL REST search response."""
        return api_response
