"""EMA (European Medicines Agency) MCP adapter.

Not fixable as on-demand query: EMA has no free public JSON REST API.
Data is available via the EMA bulk fetcher pipeline (fetchers/ema_regulatory.py).

Returns a clear error instead of a generic 500.
"""

from typing import Any

from ..base_tool import BaseMCPTool


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
