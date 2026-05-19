"""MCP Adapter: dailymed

Feature: 019-cms-puf-platform-reconciliation
"""

from urllib.parse import quote

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

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """DailyMed V2 REST API: drug name search via /spls.json endpoint.

        Default build_url produces ?query={name} which is wrong for DailyMed.
        Correct form: {base_url}/spls.json?drug_name={name}&pagesize=10
        The drug_name param filters SPLs by active ingredient / brand name.
        """
        return f"{base_url}/spls.json?drug_name={quote(drug_name)}&pagesize=10"

    def normalize(self, api_response: dict) -> dict:
        """Normalize API response to match bronze model response_body format."""
        return api_response
