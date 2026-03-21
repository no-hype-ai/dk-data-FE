"""MCP Adapter: pubmed
Feature: 015-assessment-dashboard-integration
"""
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "pubmed"

    @property
    def raw_table(self) -> str:
        return "pubmed"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """PubMed eutils esearch uses db, term, retmode parameters."""
        return f"{base_url}?db=pubmed&term={quote(drug_name)}&retmode=json&retmax=20"

    def normalize(self, api_response: dict) -> dict:
        """Normalize PubMed eutils response."""
        return api_response
