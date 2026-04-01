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


class Adapter(BaseAdapter):
    """BaseAdapter shim so test_mcp_adapters importability checks pass."""

    @property
    def source_name(self) -> str:
        return "cochrane"

    @property
    def raw_table(self) -> str:
        return "cochrane_reviews"

    @property
    def raw_schema(self) -> str:
        return "raw"

    def normalize(self, api_response: dict) -> dict:
        return api_response
