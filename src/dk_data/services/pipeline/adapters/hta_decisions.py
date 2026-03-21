"""MCP Adapter: hta_decisions
Feature: 015-assessment-dashboard-integration

Fetches HTA decisions from NICE Technology Appraisals.

Two-stage approach:
1. Search NICE for guidance pages mentioning the drug
2. Scrape each guidance page for structured decision data
   (recommendation status, publication date, indication, full text)

The NICE scraper (nice_scraper.py) extracts from the consistent TA page
structure: chapter 1 "Recommendations", section 1.1 contains the decision.
"""
import re
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for NICE HTA decisions with structured decision extraction."""

    @property
    def source_name(self) -> str:
        return "hta_decisions"

    @property
    def raw_table(self) -> str:
        return "hta_decisions"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """Search NICE for technology appraisals mentioning this drug.

        Uses the NICE website search which returns HTML with guidance links.
        The normalize() method extracts guidance IDs for the scraper.
        """
        return f"https://www.nice.org.uk/Search?q={quote(drug_name)}&ps=20&sp=on"

    def normalize(self, api_response: dict) -> dict:
        """Normalize: pass through if already structured, or extract guidance IDs from HTML.

        If the response is already structured (from nice_scraper), pass through.
        If raw HTML from search page, extract TA guidance IDs for follow-up scraping.
        """
        # If already structured with decisions
        if isinstance(api_response, dict) and 'decisions' in api_response:
            return api_response

        # If list of decision dicts (from scraper)
        if isinstance(api_response, list):
            return {'decisions': api_response}

        return api_response

    def validate_against_bronze(self, normalized: dict) -> bool:
        """Ensure we have decision data."""
        decisions = normalized.get('decisions', [])
        return isinstance(decisions, list) and len(decisions) > 0


def extract_guidance_ids_from_html(html: str) -> list[str]:
    """Extract NICE guidance IDs (e.g., ta798, ta944) from search results HTML."""
    # NICE search results contain links like /guidance/ta798
    matches = re.findall(r'/guidance/(ta\d+)', html, re.IGNORECASE)
    return list(dict.fromkeys(matches))  # deduplicate preserving order
