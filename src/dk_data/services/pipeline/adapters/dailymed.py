"""MCP Adapter: dailymed
Feature: 003-molecule-assessment-dashboard

Fetches structured drug label metadata from the DailyMed REST API (NLM).
API docs: https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm

DailyMed provides:
- SPL setid (UUID that links to openFDA's spl_set_id — entity linking key)
- SPL version and published date (label currency)
- Drug class codes (EPC classification — complements openFDA pharm_class)
- NDC codes and packaging details

No auth required. Rate limit: ~4 req/sec.
"""
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "dailymed"

    @property
    def raw_table(self) -> str:
        return "dailymed"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """Search DailyMed SPLs by drug name. Returns JSON with setid for linking."""
        return f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json?drug_name={quote(drug_name)}"

    def normalize(self, api_response: dict) -> dict:
        """Normalize DailyMed SPL search response.

        Each SPL entry has: setid (UUID), spl_version, published_date, title.
        The setid is the entity linking key to openFDA's spl_set_id.
        """
        spls = api_response.get('data', [])
        for spl in spls:
            # Parse brand name and generic name from title
            # Format: "BRAND (GENERIC) FORM [MANUFACTURER]"
            title = spl.get('title', '')
            parts = title.split(' [')
            if len(parts) == 2:
                spl['manufacturer'] = parts[1].rstrip(']')
            name_parts = parts[0].split(' (')
            if len(name_parts) >= 2:
                spl['brand_name'] = name_parts[0].strip()
                generic_rest = name_parts[1].split(')')[0]
                spl['generic_name'] = generic_rest.strip()
            # The setid links to openFDA drug_labels.spl_set_id
            spl['entity_link_key'] = spl.get('setid')
            spl['entity_link_type'] = 'spl_set_id'

        return api_response

    def validate_against_bronze(self, normalized: dict) -> bool:
        """Ensure we have at least one SPL result."""
        data = normalized.get('data', [])
        return isinstance(data, list) and len(data) > 0
