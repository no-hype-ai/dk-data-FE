"""CMS Part B Drug Spending — by HCPCS code via data-api."""

from typing import Any, Dict
from .cms_base import CMSBaseAdapter


class Adapter(CMSBaseAdapter):
    # Medicare Part B Spending by Drug
    DATASET_ID = "2nrs-ty2m"

    @property
    def source_name(self) -> str:
        return "cms_part_b_spending"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        filters = {}
        if "hcpcs_code" in query_keys:
            filters["HCPCS_Cd"] = query_keys["hcpcs_code"]
        return self.data_api_url(base_url, self.DATASET_ID, filters)

    def normalize(self, api_response: Any) -> Any:
        if isinstance(api_response, dict):
            return api_response.get("data", api_response)
        return api_response
