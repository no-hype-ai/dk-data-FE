"""MCP Adapter: sec_edgar
Feature: 015-assessment-dashboard-integration
"""
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for SEC EDGAR full-text search API responses."""

    @property
    def source_name(self) -> str:
        return "sec_edgar"

    @property
    def raw_table(self) -> str:
        return "sec_edgar"

    @property
    def raw_schema(self) -> str:
        return "raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """SEC EDGAR full-text search index."""
        return f'{base_url}?q="{quote(drug_name)}"&dateRange=custom&startdt=2020-01-01&enddt=2026-12-31'

    def normalize(self, api_response: dict) -> dict:
        """Normalize SEC EDGAR search response."""
        return api_response
