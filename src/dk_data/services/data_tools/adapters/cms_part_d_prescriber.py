"""CMS Part D Prescriber — utilization and cost data via data-api."""

from typing import Any, Dict
from .cms_base import CMSBaseAdapter


class Adapter(CMSBaseAdapter):
    # Medicare Part D Prescribers - by Provider dataset
    DATASET_ID = "eaa4-46bz"

    @property
    def source_name(self) -> str:
        return "cms_part_d_prescriber"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        filters = {}
        if "npi" in query_keys:
            filters["Prscrbr_NPI"] = query_keys["npi"]
        if "state" in query_keys:
            filters["Prscrbr_State_Abrvtn"] = query_keys["state"]
        return self.data_api_url(base_url, self.DATASET_ID, filters)

    def normalize(self, api_response: Any) -> Any:
        if isinstance(api_response, dict):
            return api_response.get("data", api_response)
        return api_response
