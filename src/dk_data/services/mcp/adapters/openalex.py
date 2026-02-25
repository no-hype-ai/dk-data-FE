"""MCP Adapter: openalex
Feature: 015-assessment-dashboard-integration
"""
from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "openalex"

    @property
    def raw_table(self) -> str:
        return "openalex"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        """Normalize OpenAlex works search response.

        OpenAlex returns scholarly works with metadata including DOI,
        title, authorships, concepts, cited_by_count, and open access
        status.  This method normalizes the response to match the
        mol_raw format.
        """
        return api_response
