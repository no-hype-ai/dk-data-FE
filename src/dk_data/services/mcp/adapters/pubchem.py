"""MCP Adapter: pubchem

Feature: 015-assessment-dashboard-integration
"""

from urllib.parse import quote

from typing import Any

from .base import BaseAdapter


_DB_LOOKUP_QUERY = """
    SELECT response_body
    FROM mol_raw.pubchem
    WHERE response_body::text ILIKE '%' || $1 || '%'
    LIMIT 20
"""


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

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(_DB_LOOKUP_QUERY, drug_name)
        if not rows:
            return None
        return {"source": "pubchem_local", "results": [dict(r) for r in rows]}
