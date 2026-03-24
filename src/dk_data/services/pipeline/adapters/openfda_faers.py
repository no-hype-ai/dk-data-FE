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
        """OpenFDA drug/event (FAERS) — fetch most recent reports for the drug.

        Uses openfda.generic_name which covers all FDA-linked reports (17K+ for
        durvalumab). Results sorted newest-first so the most recent safety signals
        are always captured.

        Limits:
          - Without API key (OPENFDA_API_KEY): openFDA caps at 100 per request.
          - With API key: 1000 per request (key is appended by _fetch_external).
        100 is used here as the safe default; if the key is present _fetch_external
        appends it and openFDA silently upgrades the effective limit to 1000.
        """
        search = f'patient.drug.openfda.generic_name:"{quote(drug_name)}"'
        return f"{base_url}?search={search}&sort=receivedate:desc&limit=100"

    def normalize(self, api_response: dict) -> dict:
        """Normalize OpenFDA drug/event (FAERS) response."""
        return api_response
