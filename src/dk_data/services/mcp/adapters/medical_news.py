"""MCP Adapter: medical_news

Feature: 015-assessment-dashboard-integration
"""

from typing import Any

from .base import BaseAdapter


_DB_LOOKUP_QUERY = """
    SELECT response_body
    FROM mol_raw.medical_news
    WHERE response_body::text ILIKE '%' || $1 || '%'
    LIMIT 20
"""


class Adapter(BaseAdapter):
    """Adapter for medical_news API responses."""

    @property
    def source_name(self) -> str:
        return "medical_news"

    @property
    def raw_table(self) -> str:
        return "medical_news"

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
        return {"source": "medical_news_local", "results": [dict(r) for r in rows]}
