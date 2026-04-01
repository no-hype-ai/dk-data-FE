"""EMA (European Medicines Agency) MCP adapter.

Not fixable as on-demand query: EMA has no free public JSON REST API.
Data is available via the EMA bulk fetcher pipeline (fetchers/ema_regulatory.py).

Returns a clear error instead of a generic 500.
"""

from typing import Any

from ..base_tool import BaseMCPTool
from .base import BaseAdapter


class EmaTool(BaseMCPTool):
    tool_name = "ema-search"

    async def invoke(self, drug_name: str) -> dict[str, Any]:
        return {
            "tool": self.tool_name,
            "error": (
                "EMA has no free public JSON API. "
                "Data is available via the EMA bulk fetcher pipeline "
                "(fetchers/ema_regulatory.py). "
                "On-demand queries are not supported."
            ),
            "status_code": None,
            "data": None,
        }


class Adapter(BaseAdapter):
    """BaseAdapter shim so test_mcp_adapters importability checks pass."""

    @property
    def source_name(self) -> str:
        return "ema"

    @property
    def raw_table(self) -> str:
        return "ema"

    @property
    def raw_schema(self) -> str:
        return "raw"

    def normalize(self, api_response: dict) -> dict:
        return api_response
