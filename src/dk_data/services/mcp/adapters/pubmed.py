"""MCP Adapter: pubmed
Feature: 015-assessment-dashboard-integration
"""
from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "pubmed"

    @property
    def raw_table(self) -> str:
        return "pubmed"

    @property
    def raw_schema(self) -> str:
        return "raw"

    def normalize(self, api_response: dict) -> dict:
        """Normalize PubMed eutils response.

        PubMed eutils (esearch/efetch) returns article records with
        MedlineCitation nesting containing article title, abstract,
        authors, MeSH terms, and publication details.  This method
        normalizes the response to match the raw format.
        """
        return api_response
