"""MCP Adapter: ema

Feature: 015-assessment-dashboard-integration
"""

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for ema API responses."""

    @property
    def source_name(self) -> str:
        return "ema"

    @property
    def raw_table(self) -> str:
        return "ema"

    @property
    def raw_schema(self) -> str:
        return "raw"

    def normalize(self, api_response: dict) -> dict:
        """Normalize API response to match bronze model response_body format."""
        return api_response
