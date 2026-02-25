"""MCP Adapter: who_icd

Feature: 015-assessment-dashboard-integration
"""

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for who_icd API responses."""

    @property
    def source_name(self) -> str:
        return "who_icd"

    @property
    def raw_table(self) -> str:
        return "who_icd"

    @property
    def raw_schema(self) -> str:
        return "raw"

    def normalize(self, api_response: dict) -> dict:
        """Normalize API response to match bronze model response_body format."""
        return api_response
