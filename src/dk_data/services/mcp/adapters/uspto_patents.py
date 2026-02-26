"""MCP Adapter: uspto_patents
Feature: 015-assessment-dashboard-integration
"""
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for USPTO patent grants API responses."""

    @property
    def source_name(self) -> str:
        return "uspto_patents"

    @property
    def raw_table(self) -> str:
        return "uspto_patents"

    @property
    def raw_schema(self) -> str:
        return "raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """USPTO patent grants API."""
        return f"{base_url}?searchText={quote(drug_name)}&start=0&rows=20"

    def normalize(self, api_response: dict) -> dict:
        """Normalize USPTO patent search response."""
        return api_response
