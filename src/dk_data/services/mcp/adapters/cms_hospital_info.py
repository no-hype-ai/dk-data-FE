"""MCP Adapter: cms_hospital_info

Feature: 015-assessment-dashboard-integration
"""

from typing import Any

from .base import BaseAdapter


_DB_LOOKUP_QUERY = """
    SELECT response_body
    FROM hcs_raw.cms_hospital_info
    WHERE response_body::text ILIKE '%' || $1 || '%'
    LIMIT 20
"""


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "cms_hospital_info"

    @property
    def raw_table(self) -> str:
        return "cms_hospital_info"

    @property
    def raw_schema(self) -> str:
        return "hcs_raw"

    def normalize(self, api_response: dict) -> dict:
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(_DB_LOOKUP_QUERY, drug_name)
        if not rows:
            return None
        return {"source": "cms_hospital_info_local", "results": [dict(r) for r in rows]}
