"""MCP Adapter: fda_drugs

Feature: 019-cms-puf-platform-reconciliation
"""

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for FDA Drugs@FDA NDA/ANDA/BLA application API responses."""

    @property
    def source_name(self) -> str:
        return "fda_drugs"

    @property
    def raw_table(self) -> str:
        return "fda_drugs"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        """Normalize API response to match bronze model response_body format."""
        return api_response
