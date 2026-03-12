"""CMS PECOS — provider enrollment and certification via data-api."""

from typing import Any, Dict
from .cms_base import CMSBaseAdapter


class Adapter(CMSBaseAdapter):
    # Medicare Fee-For-Service Public Provider Enrollment
    DATASET_ID = "fehv-95e2"

    @property
    def source_name(self) -> str:
        return "cms_pecos"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        filters = {}
        if "npi" in query_keys:
            filters["NPI"] = query_keys["npi"]
        if "state" in query_keys:
            filters["STATE"] = query_keys["state"]
        return self.data_api_url(base_url, self.DATASET_ID, filters)

    def normalize(self, api_response: Any) -> Any:
        if isinstance(api_response, dict):
            return api_response.get("data", api_response)
        return api_response
