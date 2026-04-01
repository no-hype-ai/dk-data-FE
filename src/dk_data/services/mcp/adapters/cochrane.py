"""Cochrane Library MCP adapter.

Not fixable as on-demand query: Cochrane Library requires an institutional
Wiley API key. The adapter's own docstring documents this limitation.
Data is available via the bulk fetcher pipeline (fetchers/cochrane.py).

Returns a clear error instead of a generic 500.
"""

from typing import Any

from ..base_tool import BaseMCPTool


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
