"""NICE HTA decisions MCP adapter.

Fix: Old URL hit the NICE website HTML page instead of their public search API.
Correct endpoint: api.nice.org.uk/services/search?q={drug_name}
"""

from urllib.parse import quote

from ..base_tool import BaseMCPTool


class HtaDecisionsTool(BaseMCPTool):
    tool_name = "hta-decisions-search"
    base_url = "https://api.nice.org.uk/services/search"
    raw_schema = "mol_raw"
    raw_table = "hta_decisions"

    def build_url(self, drug_name: str) -> str:
        return f"{self.base_url}?q={quote(drug_name)}"
