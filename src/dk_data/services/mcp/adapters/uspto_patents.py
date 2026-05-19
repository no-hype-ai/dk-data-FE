"""MCP Adapter: uspto_patents
Feature: 015-assessment-dashboard-integration

Uses the PatentsView API (api.patentsview.org) which replaced the
deprecated developer.uspto.gov endpoint.
"""
import json
from urllib.parse import quote

from typing import Any

from .base import BaseAdapter


_DB_LOOKUP_QUERY = """
    SELECT response_body
    FROM mol_raw.uspto_patents
    WHERE response_body::text ILIKE '%' || $1 || '%'
    LIMIT 20
"""


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
        return "mol_raw"

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

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(_DB_LOOKUP_QUERY, drug_name)
        if not rows:
            return None
        return {"source": "uspto_patents_local", "results": [dict(r) for r in rows]}
