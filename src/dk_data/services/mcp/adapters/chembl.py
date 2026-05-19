"""ChEMBL MCP adapter — DB-first BaseAdapter over mol_raw.chembl.

Backlog-tier adapter (#415 WS3). Serves from the raw landing table via the
JSONB `response_body` convention (mirrors openfda_labels.Adapter); exact
column/path refinement is deferred until the source's bronze/silver model
lands. db_query honors the BaseAdapter contract: dict on hit, None on a
genuine miss, and a real DB error PROPAGATES (never swallowed to None — a
DB outage is not a cache miss; the router maps a raised error to 502).
"""

from typing import Any

from .base import BaseAdapter

_DB_LOOKUP_QUERY = """
    SELECT response_body
    FROM mol_raw.chembl
    WHERE response_body::text ILIKE '%' || $1 || '%'
    LIMIT 20
"""


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "chembl"

    @property
    def raw_table(self) -> str:
        return "chembl"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(_DB_LOOKUP_QUERY, drug_name)
        if not rows:
            return None
        return {"source": "chembl_local", "results": [dict(r) for r in rows]}
