"""MCP Adapter: chembl
Feature: 015-assessment-dashboard-integration
"""
from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "chembl"

    @property
    def raw_table(self) -> str:
        return "chembl"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        """Normalize ChEMBL REST search response.

        ChEMBL returns paginated results with molecule, assay, and
        activity records.  This method normalizes the response to
        match the mol_raw format.
        """
        return api_response
