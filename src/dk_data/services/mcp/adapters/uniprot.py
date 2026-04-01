"""MCP Adapter: uniprot
Feature: 015-assessment-dashboard-integration
"""
from urllib.parse import quote

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

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """UniProt REST search: ?query= is correct but format=json must be explicit.

        Without format=json the server uses content negotiation which may return
        a non-JSON representation. size=10 limits results to avoid large payloads.
        """
        return f"{base_url}?query={quote(drug_name)}&format=json&size=10"

    def normalize(self, api_response: dict) -> dict:
        """Normalize UniProt REST search response.

        UniProt returns protein records with accession, protein names,
        gene names, organism, sequence, and function annotations.
        This method normalizes the response to match the mol_raw
        format.
        """
        return api_response
