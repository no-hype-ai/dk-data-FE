"""MCP Adapter: clinicaltrials
Feature: 015-assessment-dashboard-integration
"""
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

    def normalize(self, api_response: dict) -> dict:
        """Normalize ClinicalTrials.gov v2 search response.

        The v2 API nests most fields under protocolSection, which
        contains identificationModule, statusModule, descriptionModule,
        designModule, etc.  This method flattens the protocolSection
        nesting to match the mol_raw format.
        """
        return api_response
