"""RCSB PDB structures MCP adapter.

Fix: PDB v2 search API requires a structured JSON payload in the ?json= parameter,
not a plain ?query= string. Default base pattern returned HTTP 400.
"""

import json
from typing import Any
from urllib.parse import quote

from ..base_tool import BaseMCPTool
from .base import BaseAdapter


class PdbStructuresTool(BaseMCPTool):
    tool_name = "pdb-search"
    base_url = "https://search.rcsb.org/rcsbsearch/v2/query"

    def build_url(self, drug_name: str) -> str:
        payload = {
            "query": {
                "type": "terminal",
                "service": "text",
                "parameters": {"value": drug_name},
            },
            "return_type": "entry",
            "request_options": {"return_all_hits": False},
        }
        encoded = quote(json.dumps(payload, separators=(",", ":")))
        return f"{self.base_url}?json={encoded}"


_PDB_STRUCTURES_DB_QUERY = """
    SELECT response_body
    FROM mol_raw.pdb_structures
    WHERE response_body::text ILIKE '%' || $1 || '%'
    LIMIT 20
"""


class Adapter(BaseAdapter):
    """DB-first backlog adapter over mol_raw.pdb_structures (#415 WS3).

    JSONB response_body serving convention (mirrors openfda_labels.Adapter);
    exact path refinement deferred. db_query: dict on hit, None on genuine
    miss, real DB error PROPAGATES (never swallowed — router maps to 502).
    """

    @property
    def source_name(self) -> str:
        return "pdb_structures"

    @property
    def raw_table(self) -> str:
        return "pdb_structures"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(_PDB_STRUCTURES_DB_QUERY, drug_name)
        if not rows:
            return None
        return {"source": "pdb_structures_local", "results": [dict(r) for r in rows]}
