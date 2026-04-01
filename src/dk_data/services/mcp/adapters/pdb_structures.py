"""RCSB PDB structures MCP adapter.

Fix: PDB v2 search API requires a structured JSON payload in the ?json= parameter,
not a plain ?query= string. Default base pattern returned HTTP 400.
"""

import json
from urllib.parse import quote

from ..base_tool import BaseMCPTool


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
