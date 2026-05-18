"""OpenFDA Drug Labels MCP adapter.

Searches FDA drug label (SPL) data by generic name.
API: https://api.fda.gov/drug/label.json
"""

from urllib.parse import quote

from ..base_tool import BaseMCPTool


class OpenFDALabelsTool(BaseMCPTool):
    tool_name = "openfda-labels-search"
    base_url = "https://api.fda.gov/drug/label.json"

    def build_url(self, drug_name: str) -> str:
        encoded = quote(f'openfda.generic_name:"{drug_name}"')
        return f"{self.base_url}?search={encoded}&limit=5"
