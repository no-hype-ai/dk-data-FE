"""MCP Adapter: uniprot
Feature: 015-assessment-dashboard-integration
"""
from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "uniprot"

    @property
    def raw_table(self) -> str:
        return "uniprot"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        """Normalize UniProt REST search response.

        UniProt returns protein records with accession, protein names,
        gene names, organism, sequence, and function annotations.
        This method normalizes the response to match the mol_raw
        format.
        """
        return api_response
