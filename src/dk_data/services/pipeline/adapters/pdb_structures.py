"""MCP Adapter: pdb_structures

Feature: 015-assessment-dashboard-integration
"""

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for pdb_structures API responses."""

    @property
    def source_name(self) -> str:
        return "pdb_structures"

    @property
    def raw_table(self) -> str:
        return "pdb_structures"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        """Normalize API response to match bronze model response_body format."""
        return api_response
