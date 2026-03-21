"""MCP Adapter: journal_rss

Feature: 015-assessment-dashboard-integration
"""

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for journal_rss API responses."""

    @property
    def source_name(self) -> str:
        return "journal_rss"

    @property
    def raw_table(self) -> str:
        return "journal_rss"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        """Normalize API response to match bronze model response_body format."""
        return api_response
