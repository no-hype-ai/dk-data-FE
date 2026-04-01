"""MCP Adapter: euipo_trademarks

Feature: 015-assessment-dashboard-integration
"""

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for euipo_trademarks API responses."""

    @property
    def source_name(self) -> str:
        return "euipo_trademarks"

    @property
    def raw_table(self) -> str:
        return "euipo_trademarks"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        """Normalize API response to match bronze model response_body format."""
        return api_response
