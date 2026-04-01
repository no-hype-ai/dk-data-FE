"""FDA Drugs (OpenFDA) MCP adapter.

Fix: FDA API uses ?search= not ?query=. The default base pattern returned HTTP 400.
Correct URL: search=openfda.generic_name:"{drug_name}"&limit=100
"""

from urllib.parse import quote

from ..base_tool import BaseMCPTool


class FdaDrugsTool(BaseMCPTool):
    tool_name = "fda-drugs-search"
    base_url = "https://api.fda.gov/drug/drugsfda.json"
    raw_schema = "mol_raw"
    raw_table = "fda_drugs"

    def build_url(self, drug_name: str) -> str:
        encoded = quote(f'openfda.generic_name:"{drug_name}"')
        return f"{self.base_url}?search={encoded}&limit=100"
