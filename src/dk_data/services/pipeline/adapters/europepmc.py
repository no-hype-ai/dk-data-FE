"""MCP Adapter: europepmc
Feature: europepmc-integration

Per-molecule triggered retrieval from Europe PMC REST API.
Called when xenon triggers POST /api/v1/data-platform/ingest/europepmc.

Unique value vs OpenAlex:
  - Full-text availability for PMC articles (inEPMC=Y)
  - Biomedical entity annotations (genes, diseases, chemicals)
  - NCT → publication cross-links via LINKED_CTID
  - Preprint coverage (PPR source: bioRxiv, medRxiv)
"""
from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "europepmc"

    @property
    def raw_table(self) -> str:
        return "europepmc"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """EuropePMC search with resultType=core for full metadata including abstracts."""
        encoded = quote(f'"{drug_name}"')
        return (
            f"{base_url}/search"
            f"?query={encoded}"
            f"&format=json"
            f"&pageSize=50"
            f"&resultType=core"
            f"&sort=P_PDATE_D"
        )

    def normalize(self, api_response: dict) -> dict:
        """Normalize EuropePMC search response.

        Raw response shape:
          { "resultList": { "result": [...] }, "nextCursorMark": "..." }
        """
        return api_response
