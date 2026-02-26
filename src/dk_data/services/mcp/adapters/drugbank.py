"""MCP Adapter: drugbank
Feature: 015-assessment-dashboard-integration
"""
from urllib.parse import quote

from .base import BaseAdapter


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
        """DrugBank API search. Note: requires API key for production use."""
        return f"{base_url}?q={quote(drug_name)}"

    def normalize(self, api_response: dict) -> dict:
        """Normalize DrugBank search response."""
        return api_response
