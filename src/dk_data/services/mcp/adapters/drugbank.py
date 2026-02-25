"""MCP Adapter: drugbank
Feature: 015-assessment-dashboard-integration
"""
from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "drugbank"

    @property
    def raw_table(self) -> str:
        return "drugbank"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        """Normalize DrugBank REST JSON response.

        DrugBank returns detailed drug records including identifiers,
        pharmacology, interactions, and pathway data.  This method
        normalizes the response to match the mol_raw format.
        """
        return api_response
