"""MCP Adapter: openfda_labels
Feature: 015-assessment-dashboard-integration
"""
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "openfda_labels"

    @property
    def raw_table(self) -> str:
        return "openfda_labels"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """OpenFDA drug/label uses search parameter with openfda field queries."""
        return f'{base_url}?search=openfda.generic_name:"{quote(drug_name)}"&limit=5'

    def normalize(self, api_response: dict) -> dict:
        """Normalize OpenFDA drug/label response."""
        return api_response
