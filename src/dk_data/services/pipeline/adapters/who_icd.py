"""MCP Adapter: who_icd

Feature: 015-assessment-dashboard-integration

WHO ICD-11 API requires OAuth2 client credentials authentication.
Token management is handled in base_tool.py._get_who_icd_token().
"""
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for WHO ICD-11 API responses."""

    @property
    def source_name(self) -> str:
        return "who_icd"

    @property
    def raw_table(self) -> str:
        return "who_icd"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """WHO ICD-11 search endpoint.

        Uses the linearization search:
        https://id.who.int/icd/release/11/2024-01/mms/search?q=...
        """
        return f"{base_url}?q={quote(drug_name)}&flatResults=true&useFlexisearch=true"

    def normalize(self, api_response: dict) -> dict:
        """Normalize WHO ICD-11 search response."""
        return api_response
