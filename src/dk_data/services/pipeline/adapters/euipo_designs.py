"""MCP Adapter: euipo_designs

Feature: 014-uspto-euipo-model-datasource
"""

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for euipo_designs API responses."""

    @property
    def source_name(self) -> str:
        return "euipo_designs"

    @property
    def raw_table(self) -> str:
        return "euipo_designs"

    @property
    def raw_schema(self) -> str:
        return "raw"

    def normalize(self, api_response: dict) -> dict:
        """Normalize API response to match bronze model response_body format."""
        return api_response
