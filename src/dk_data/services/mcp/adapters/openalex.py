"""MCP Adapter: openalex
Feature: 015-assessment-dashboard-integration
"""
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "openalex"

    @property
    def raw_table(self) -> str:
        return "openalex"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """OpenAlex works API uses filter parameter for search."""
        return f"{base_url}?filter=display_name.search:{quote(drug_name)}&per_page=20"

    def normalize(self, api_response: dict) -> dict:
        """Normalize OpenAlex works search response."""
        return api_response
