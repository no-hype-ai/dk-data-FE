"""MCP Adapter: uspto_patents
Feature: 015-assessment-dashboard-integration

Uses the PatentsView API (api.patentsview.org) which replaced the
deprecated developer.uspto.gov endpoint.
"""
import json
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for USPTO PatentsView API responses."""

    @property
    def source_name(self) -> str:
        return "uspto_patents"

    @property
    def raw_table(self) -> str:
        return "uspto_patents"

    @property
    def raw_schema(self) -> str:
        return "raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """PatentsView API v1 query endpoint.

        Uses the POST-style query via GET params:
        https://api.patentsview.org/patents/query?q=...&f=...&o=...
        """
        q = json.dumps({"_text_any": {"patent_abstract": drug_name}})
        f = json.dumps(["patent_number", "patent_title", "patent_date",
                         "patent_abstract", "assignees"])
        o = json.dumps({"page": 1, "per_page": 25})
        return f"{base_url}?q={quote(q)}&f={quote(f)}&o={quote(o)}"

    def normalize(self, api_response: dict) -> dict:
        """Normalize PatentsView response."""
        return api_response
