"""MCP Adapter: pubchem

Feature: 015-assessment-dashboard-integration
"""

from urllib.parse import quote

from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "pubchem"

    @property
    def raw_table(self) -> str:
        return "pubchem"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """PubChem PUG REST requires the compound name in the URL path, not a query param.

        Correct:  .../rest/pug/compound/name/{name}/JSON
        Default (wrong): .../rest/pug/compound/name?query={name}
        """
        return f"{base_url}/{quote(drug_name)}/JSON"

    def normalize(self, api_response: dict) -> dict:
        return api_response
