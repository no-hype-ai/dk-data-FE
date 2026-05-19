"""Cochrane Library MCP adapter.

Not fixable as on-demand query: Cochrane Library requires an institutional
Wiley API key. The adapter's own docstring documents this limitation.
Data is available via the bulk fetcher pipeline (fetchers/cochrane.py).

Returns a clear error instead of a generic 500.
"""

from typing import Any

from ..base_tool import BaseMCPTool
from .base import BaseAdapter


class CochraneTool(BaseMCPTool):
    tool_name = "cochrane-search"

    async def invoke(self, drug_name: str) -> dict[str, Any]:
        return {
            "tool": self.tool_name,
            "error": (
                "Cochrane Library requires an institutional Wiley API key. "
                "Data is available via the bulk fetcher pipeline "
                "(fetchers/cochrane.py). "
                "On-demand queries are not supported without credentials."
            ),
            "status_code": None,
            "data": None,
        }


_COCHRANE_DB_QUERY = """
    SELECT response_body
    FROM mol_raw.cochrane_reviews
    WHERE response_body::text ILIKE '%' || $1 || '%'
    LIMIT 20
"""


class Adapter(BaseAdapter):
    """DB-first backlog adapter over mol_raw.cochrane_reviews (#415 WS3).

    JSONB response_body serving convention (mirrors openfda_labels.Adapter);
    exact path refinement deferred. db_query: dict on hit, None on genuine
    miss, real DB error PROPAGATES (never swallowed — router maps to 502).
    """

    @property
    def source_name(self) -> str:
        return "cochrane"

    @property
    def raw_table(self) -> str:
        return "cochrane_reviews"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(_COCHRANE_DB_QUERY, drug_name)
        if not rows:
            return None
        return {"source": "cochrane_local", "results": [dict(r) for r in rows]}
