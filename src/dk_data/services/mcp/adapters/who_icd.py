"""MCP Adapter: who_icd

Feature: 015-assessment-dashboard-integration

WHO ICD-11 API requires OAuth2 client credentials authentication.
Token management is handled in base_tool.py._get_who_icd_token().
"""
from urllib.parse import quote

from typing import Any

from .base import BaseAdapter


_DB_LOOKUP_QUERY = """
    SELECT response_body
    FROM mol_raw.who_icd
    WHERE response_body::text ILIKE '%' || $1 || '%'
    LIMIT 20
"""


class Adapter(BaseAdapter):
    """Adapter for WHO ICD-11 API responses."""

    @property
    def source_name(self) -> str:
        return "who_icd"

    @property
    def raw_table(self) -> str:
        return "who_icd"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """WHO ICD-11 search endpoint.

        Uses the linearization search:
        https://id.who.int/icd/release/11/2024-01/mms/search?q=...
        """
        return f"{base_url}?q={quote(drug_name)}&flatResults=true&useFlexisearch=true"

    def normalize(self, api_response: dict) -> dict:
        """Normalize WHO ICD-11 search response."""
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(_DB_LOOKUP_QUERY, drug_name)
        if not rows:
            return None
        return {"source": "who_icd_local", "results": [dict(r) for r in rows]}
