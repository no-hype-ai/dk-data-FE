"""MCP Adapter: orange_book
Feature: 015-assessment-dashboard-integration
"""
from urllib.parse import quote

from typing import Any

from .base import BaseAdapter


_DB_LOOKUP_QUERY = """
    SELECT response_body
    FROM mol_raw.orange_book
    WHERE response_body::text ILIKE '%' || $1 || '%'
    LIMIT 20
"""


class Adapter(BaseAdapter):
    """Adapter for FDA Drugs@FDA (Orange Book) API responses."""

    @property
    def source_name(self) -> str:
        return "orange_book"

    @property
    def raw_table(self) -> str:
        return "orange_book"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """FDA Drugs@FDA API uses openFDA search syntax."""
        return f'{base_url}?search=openfda.generic_name:"{quote(drug_name)}"&limit=5'

    def normalize(self, api_response: dict) -> dict:
        """Normalize API response to match bronze model response_body format."""
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(_DB_LOOKUP_QUERY, drug_name)
        if not rows:
            return None
        return {"source": "orange_book_local", "results": [dict(r) for r in rows]}
