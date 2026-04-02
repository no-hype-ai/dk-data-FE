"""MCP Adapter: orange_book
Feature: 015-assessment-dashboard-integration
"""
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for FDA Drugs@FDA (Orange Book) API responses."""

    @property
    def source_name(self) -> str:
        return "orange_book"

    @property
    def raw_table(self) -> str:
        return "orange_book"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """FDA Drugs@FDA API uses openFDA search syntax."""
        return f'{base_url}?search=openfda.generic_name:"{quote(drug_name)}"&limit=5'

    def normalize(self, api_response: dict) -> dict:
        """Normalize API response to match bronze model response_body format."""
        return api_response
