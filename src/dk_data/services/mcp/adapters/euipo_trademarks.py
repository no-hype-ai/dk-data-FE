"""MCP Adapter: euipo_trademarks

Feature: 015-assessment-dashboard-integration
"""

from typing import Any

from .base import BaseAdapter


_DB_LOOKUP_QUERY = """
    SELECT response_body
    FROM mol_raw.euipo_trademarks
    WHERE response_body::text ILIKE '%' || $1 || '%'
    LIMIT 20
"""


class Adapter(BaseAdapter):
    """Adapter for euipo_trademarks API responses."""

    @property
    def source_name(self) -> str:
        return "euipo_trademarks"

    @property
    def raw_table(self) -> str:
        return "euipo_trademarks"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        """Normalize API response to match bronze model response_body format."""
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(_DB_LOOKUP_QUERY, drug_name)
        if not rows:
            return None
        return {"source": "euipo_trademarks_local", "results": [dict(r) for r in rows]}
