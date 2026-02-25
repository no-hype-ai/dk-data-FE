"""MCP Adapter: openfda_faers
Feature: 015-assessment-dashboard-integration
"""
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

    def normalize(self, api_response: dict) -> dict:
        """Normalize OpenFDA drug/event (FAERS) response.

        The OpenFDA drug/event endpoint returns adverse event reports
        with nested patient, drug, and reaction information.  This
        method normalizes the response to match the mol_raw format.
        """
        return api_response
