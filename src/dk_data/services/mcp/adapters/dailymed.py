"""MCP Adapter: dailymed

Feature: 019-cms-puf-platform-reconciliation
"""

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for NLM DailyMed SPL API responses."""

    @property
    def source_name(self) -> str:
        return "dailymed"

    @property
    def raw_table(self) -> str:
        return "dailymed"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        """Normalize API response to match bronze model response_body format."""
        return api_response
