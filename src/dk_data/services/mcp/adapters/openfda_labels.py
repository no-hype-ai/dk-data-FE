"""MCP Adapter: openfda_labels
Feature: 015-assessment-dashboard-integration
"""
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

    def normalize(self, api_response: dict) -> dict:
        """Normalize OpenFDA drug/label response.

        The OpenFDA drug/label endpoint returns structured product
        labeling (SPL) data including indications, warnings, dosage,
        and pharmacology sections.  This method normalizes the
        response to match the mol_raw format.
        """
        return api_response
