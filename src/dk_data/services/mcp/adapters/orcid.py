"""ORCID search MCP adapter.

Fixes:
  1. ORCID API uses ?q= not ?query=
  2. ORCID returns XML by default — requires Accept: application/json header
     (base_tool.py now sends this by default, but explicit here for clarity)
"""

from typing import Any
from urllib.parse import quote

from ..base_tool import BaseMCPTool
from .base import BaseAdapter


class OrcidTool(BaseMCPTool):
    tool_name = "orcid-search"
    base_url = "https://pub.orcid.org/v3.0/search/"

    def build_url(self, drug_name: str) -> str:
        return f"{self.base_url}?q={quote(drug_name)}"

    def build_headers(self) -> dict[str, str]:
        # Explicit override — ORCID defaults to XML without this
        return {"Accept": "application/json"}


_ORCID_DB_QUERY = """
    SELECT response_body
    FROM mol_raw.orcid
    WHERE response_body::text ILIKE '%' || $1 || '%'
    LIMIT 20
"""


class Adapter(BaseAdapter):
    """DB-first backlog adapter over mol_raw.orcid (#415 WS3).

    JSONB response_body serving convention (mirrors openfda_labels.Adapter);
    exact path refinement deferred. db_query: dict on hit, None on genuine
    miss, real DB error PROPAGATES (never swallowed — router maps to 502).
    """

    @property
    def source_name(self) -> str:
        return "orcid"

    @property
    def raw_table(self) -> str:
        return "orcid"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(_ORCID_DB_QUERY, drug_name)
        if not rows:
            return None
        return {"source": "orcid_local", "results": [dict(r) for r in rows]}
