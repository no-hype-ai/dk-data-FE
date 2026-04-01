"""MCP Adapter: cochrane_reviews

Feature: 015-assessment-dashboard-integration

NOTE: The Cochrane Library has no free public JSON REST API.
The api_base_url in the tool registry (/cdsr/reviews) is an HTML web page.
The search URL below is the correct search endpoint but also returns HTML
without a Wiley session cookie / institutional API token.

To enable this tool, provision a Wiley Online Library API key and add it
to dk-data-secrets as COCHRANE_API_KEY. Until then, invocations will fail
with a 500 (JSONDecodeError on the HTML response).
"""
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for cochrane_reviews API responses."""

    @property
    def source_name(self) -> str:
        return "cochrane_reviews"

    @property
    def raw_table(self) -> str:
        return "cochrane_reviews"

    @property
    def raw_schema(self) -> str:
        return "raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """Build Cochrane Library search URL.

        The registry api_base_url (/cdsr/reviews) is an HTML page — override
        it entirely to use the search endpoint. Requires Wiley auth to return
        JSON; without auth BaseMCPTool will raise JSONDecodeError → 500.
        """
        return f"https://www.cochranelibrary.com/search?q={quote(drug_name)}&t=13"

    def normalize(self, api_response: dict) -> dict:
        """Normalize API response to match bronze model response_body format."""
        return api_response
