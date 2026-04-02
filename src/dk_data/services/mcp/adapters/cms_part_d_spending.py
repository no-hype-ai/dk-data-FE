"""CMS Part D Drug Spending MCP adapter.

Fix: Old URL hit the CMS data catalog HTML page instead of the data API.
CMS migrated to a new data-api endpoint (related to #152 CMS CKAN deprecation).
Dataset UUID: 0b8e6f28-9458-4532-9b85-f39d2a4da3e9 (CMS Part D spending by drug).
"""

from urllib.parse import quote

from ..base_tool import BaseMCPTool

_DATASET_UUID = "0b8e6f28-9458-4532-9b85-f39d2a4da3e9"


class CmsPartDSpendingTool(BaseMCPTool):
    tool_name = "cms-part-d-spending"

    def build_url(self, drug_name: str) -> str:
        encoded = quote(drug_name)
        return (
            f"https://data.cms.gov/data-api/v1/dataset/{_DATASET_UUID}/data"
            f"?filter[Brnd_Name]={encoded}"
        )
