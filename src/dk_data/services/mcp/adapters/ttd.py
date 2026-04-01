"""TTD (Therapeutic Targets Database) MCP adapter.

Not fixable as on-demand query:
  - Domain (db.idrblab.net) redirects to ttd.idrblab.cn (Chinese domain)
  - ttd.idrblab.cn is unreachable from outside China (confirmed timeout)
  - TTD is a flat-file database with no REST API

Data is available via the bulk fetcher pipeline.
Returns a clear error instead of a redirect timeout.
"""

from typing import Any

from ..base_tool import BaseMCPTool


class TtdTool(BaseMCPTool):
    tool_name = "ttd-search"

    async def invoke(self, drug_name: str) -> dict[str, Any]:
        return {
            "tool": self.tool_name,
            "error": (
                "TTD (Therapeutic Targets Database) is a bulk-only source. "
                "The domain redirects to ttd.idrblab.cn which is unreachable "
                "from outside China. "
                "Data is available via the bulk fetcher pipeline."
            ),
            "status_code": None,
            "data": None,
        }
