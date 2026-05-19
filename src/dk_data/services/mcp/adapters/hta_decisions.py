"""NICE HTA decisions MCP adapter.

Fix: Old URL hit the NICE website HTML page instead of their public search API.
Correct endpoint: api.nice.org.uk/services/search?q={drug_name}
"""

from urllib.parse import quote

from ..base_tool import BaseMCPTool
from typing import Any

from .base import BaseAdapter


_HTA_DECISIONS_DB_QUERY = """
    SELECT response_body
    FROM mol_raw.hta_decisions
    WHERE response_body::text ILIKE '%' || $1 || '%'
    LIMIT 20
"""


class HtaDecisionsTool(BaseMCPTool):
    tool_name = "hta-decisions-search"
    base_url = "https://api.nice.org.uk/services/search"

    def build_url(self, drug_name: str) -> str:
        return f"{self.base_url}?q={quote(drug_name)}"


class Adapter(BaseAdapter):
    """BaseAdapter shim so test_mcp_adapters importability checks pass."""

    @property
    def source_name(self) -> str:
        return "hta_decisions"

    @property
    def raw_table(self) -> str:
        return "hta_decisions"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(_HTA_DECISIONS_DB_QUERY, drug_name)
        if not rows:
            return None
        return {"source": "hta_decisions_local", "results": [dict(r) for r in rows]}
