"""MCP Adapter: WHO Global Health Observatory (GHO)
Feature: 003-molecule-assessment-dashboard

Fetches disease-level incidence, prevalence, and mortality from the WHO GHO OData API.
The drug_name parameter is repurposed as indication/disease name.
"""
from urllib.parse import quote

from .base import BaseAdapter

# WHO GHO indicator codes for common disease categories
INDICATOR_MAP = {
    # NCD mortality probability (30-70) — broad fallback
    'default': 'NCDMORT3070',
    # Cancer-specific indicators
    'breast cancer': 'SA_0000001438',
    'cervical cancer': 'SA_0000001462',
}


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "who_gho"

    @property
    def raw_table(self) -> str:
        return "who_gho"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """Build WHO GHO OData query URL.

        drug_name is repurposed as the indication/disease name.
        Selects the best indicator code for the disease, then queries
        the GHO API filtered to USA data from 2018 onward.
        """
        indication = drug_name.lower().strip()
        indicator = INDICATOR_MAP.get(indication, INDICATOR_MAP['default'])

        # Allow override via params
        if params.get('indicator'):
            indicator = params['indicator']

        # WHO GHO OData endpoint: /api/{IndicatorCode}?$filter=...
        gho_base = "https://ghoapi.azureedge.net/api"
        filter_expr = quote("SpatialDim eq 'USA' and TimeDim ge 2018")
        return f"{gho_base}/{indicator}?$filter={filter_expr}"

    def normalize(self, api_response: dict) -> dict:
        """Normalize WHO GHO OData response.

        GHO returns { value: [ { IndicatorCode, SpatialDim, TimeDim, NumericValue, ... } ] }
        We preserve the full response for bronze extraction.
        """
        return api_response

    def validate_against_bronze(self, normalized: dict) -> bool:
        """Ensure the response has at least one data point."""
        values = normalized.get('value', [])
        return isinstance(values, list) and len(values) > 0
