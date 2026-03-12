"""CMS DMEPOS — Durable Medical Equipment utilization via data-api."""

from typing import Any, Dict
from .cms_base import CMSBaseAdapter


class Adapter(CMSBaseAdapter):
    # DMEPOS Referring Providers
    DATASET_ID = "his4-ibbw"

    @property
    def source_name(self) -> str:
        return "cms_dmepos"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        filters = {}
        if "npi" in query_keys:
            filters["Rfrg_NPI"] = query_keys["npi"]
        if "hcpcs_code" in query_keys:
            filters["HCPCS_Cd"] = query_keys["hcpcs_code"]
        return self.data_api_url(base_url, self.DATASET_ID, filters)

    def normalize(self, api_response: Any) -> Any:
        if isinstance(api_response, dict):
            return api_response.get("data", api_response)
        return api_response
