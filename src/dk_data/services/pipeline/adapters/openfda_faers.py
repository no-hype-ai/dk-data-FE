"""MCP Adapter: openfda_faers
Feature: 015-assessment-dashboard-integration
"""
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "openfda_faers"

    @property
    def raw_table(self) -> str:
        return "openfda_faers"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """OpenFDA drug/event (FAERS) uses search parameter with field queries."""
        return f'{base_url}?search=patient.drug.openfda.generic_name:"{quote(drug_name)}"&limit=10'

    def normalize(self, api_response: dict) -> dict:
        """Normalize OpenFDA drug/event (FAERS) response."""
        return api_response
