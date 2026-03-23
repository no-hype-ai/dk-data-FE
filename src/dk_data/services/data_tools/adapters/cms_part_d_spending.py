"""CMS Part D Drug Spending — spending dashboard data via data-api."""

from typing import Any, Dict
from .cms_base import CMSBaseAdapter


class Adapter(CMSBaseAdapter):
    # Medicare Part D Spending by Drug
    DATASET_ID = "7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b"

    @property
    def source_name(self) -> str:
        return "cms_part_d_spending"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        filters = {}
        if "drug_name" in query_keys:
            filters["Brnd_Name"] = query_keys["drug_name"]
        return self.data_api_url(base_url, self.DATASET_ID, filters)

    def normalize(self, api_response: Any) -> Any:
        if isinstance(api_response, dict):
            return api_response.get("data", api_response)
        return api_response
