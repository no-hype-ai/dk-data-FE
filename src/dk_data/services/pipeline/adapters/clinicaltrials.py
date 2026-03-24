"""MCP Adapter: clinicaltrials
Feature: 015-assessment-dashboard-integration
"""
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "clinicaltrials"

    @property
    def raw_table(self) -> str:
        return "clinicaltrials"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """ClinicalTrials.gov v2 API — query.intr targets the drug intervention field.

        query.term is broad text search (titles, descriptions) and returns too many
        off-target results. query.intr searches the intervention/drug fields specifically,
        matching only trials where the drug is an actual intervention.
        countTotal=true returns the totalCount so consumers know how many trials exist.
        """
        return f"{base_url}?query.intr={quote(drug_name)}&countTotal=true&pageSize=50"

    def normalize(self, api_response: dict) -> dict:
        """Normalize ClinicalTrials.gov v2 search response."""
        return api_response
