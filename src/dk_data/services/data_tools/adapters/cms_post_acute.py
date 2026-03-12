"""CMS Post-Acute Care — quality and utilization via data-api."""

from typing import Any, Dict
from .cms_base import CMSBaseAdapter


class Adapter(CMSBaseAdapter):
    # Post-Acute Care Providers
    DATASET_ID = "nrth-mfg3"

    @property
    def source_name(self) -> str:
        return "cms_post_acute"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        filters = {}
        if "ccn" in query_keys:
            filters["CCN"] = query_keys["ccn"]
        return self.data_api_url(base_url, self.DATASET_ID, filters)

    def normalize(self, api_response: Any) -> Any:
        if isinstance(api_response, dict):
            return api_response.get("data", api_response)
        return api_response
