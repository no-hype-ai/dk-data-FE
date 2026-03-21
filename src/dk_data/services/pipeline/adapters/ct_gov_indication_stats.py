"""MCP Adapter: ClinicalTrials.gov Indication Statistics
Feature: 003-molecule-assessment-dashboard

Fetches trial counts per indication/condition from CT.gov v2 API.
The drug_name parameter is repurposed as condition/indication name.
"""
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "ct_gov_indication_stats"

    @property
    def raw_table(self) -> str:
        return "ct_gov_indication_stats"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """Build ClinicalTrials.gov v2 query for indication trial counts.

        drug_name is repurposed as the condition/disease name.
        Uses countTotal=true&pageSize=0 to get just the count without study data.
        """
        condition = quote(drug_name.strip())
        ct_base = "https://clinicaltrials.gov/api/v2/studies"

        # Phase filter: optionally restrict to Phase 3
        phase_filter = ""
        if params.get('phase'):
            phase_filter = f"&filter.phase={params['phase']}"

        return f"{ct_base}?query.cond={condition}&countTotal=true&pageSize=0{phase_filter}"

    def normalize(self, api_response: dict) -> dict:
        """Normalize CT.gov v2 response.

        CT.gov v2 returns { totalCount: N, studies: [] } when pageSize=0.
        We store the totalCount plus the query condition for bronze extraction.
        """
        return api_response

    def validate_against_bronze(self, normalized: dict) -> bool:
        """Ensure totalCount is present."""
        return 'totalCount' in normalized
