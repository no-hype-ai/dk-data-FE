"""SEC EDGAR MCP adapter — DB-first backlog adapter (#415 WS3).

Serves from mol_raw.sec_edgar via JSONB response_body; exact path
refinement deferred. Mirrors the openfda_labels.Adapter convention.
"""

from typing import Any

from .base import BaseAdapter

_SEC_EDGAR_DB_QUERY = """
    SELECT response_body
    FROM mol_raw.sec_edgar
    WHERE response_body::text ILIKE '%' || $1 || '%'
    LIMIT 20
"""


class Adapter(BaseAdapter):
    """DB-first backlog adapter over mol_raw.sec_edgar (#415 WS3).

    JSONB response_body serving convention (mirrors openfda_labels.Adapter);
    exact path refinement deferred. db_query: dict on hit, None on genuine
    miss, real DB error PROPAGATES (never swallowed — router maps to 502).
    """

    @property
    def source_name(self) -> str:
        return "sec_edgar"

    @property
    def raw_table(self) -> str:
        return "sec_edgar"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(_SEC_EDGAR_DB_QUERY, drug_name)
        if not rows:
            return None
        return {"source": "sec_edgar_local", "results": [dict(r) for r in rows]}
