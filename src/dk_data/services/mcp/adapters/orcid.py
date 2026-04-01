"""ORCID search MCP adapter.

Fixes:
  1. ORCID API uses ?q= not ?query=
  2. ORCID returns XML by default — requires Accept: application/json header
     (base_tool.py now sends this by default, but explicit here for clarity)
"""

from urllib.parse import quote

from ..base_tool import BaseMCPTool


class OrcidTool(BaseMCPTool):
    tool_name = "orcid-search"
    base_url = "https://pub.orcid.org/v3.0/search/"
    raw_schema = "mol_raw"
    raw_table = "orcid"

    def build_url(self, drug_name: str) -> str:
        return f"{self.base_url}?q={quote(drug_name)}"

    def build_headers(self) -> dict[str, str]:
        # Explicit override — ORCID defaults to XML without this
        return {"Accept": "application/json"}
