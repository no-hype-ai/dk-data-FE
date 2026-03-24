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
        """OpenFDA drug/event (FAERS) — fetch 1000 most recent reports for the drug.

        Searches openfda.generic_name OR openfda.brand_name to maximise coverage
        (both fields resolve to the same reports for most drugs, but OR catches
        cases where only one is populated). Results sorted newest-first.
        openFDA hard cap: skip+limit ≤ 25,000; limit=1000 is the per-request max.
        """
        q_generic = f'patient.drug.openfda.generic_name:"{quote(drug_name)}"'
        q_brand   = f'patient.drug.openfda.brand_name:"{quote(drug_name)}"'
        search    = f"({q_generic}+{q_brand})"
        return f"{base_url}?search={search}&sort=receivedate:desc&limit=1000"

    def normalize(self, api_response: dict) -> dict:
        """Normalize OpenFDA drug/event (FAERS) response."""
        return api_response
