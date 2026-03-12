"""CMS Geographic Variation — Medicare spending/utilization by geography via data-api."""

from typing import Any, Dict
from .cms_base import CMSBaseAdapter


class Adapter(CMSBaseAdapter):
    # Geographic Variation Public Use File
    DATASET_ID = "cxae-5wc9"

    @property
    def source_name(self) -> str:
        return "cms_geographic_variation"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        filters = {}
        if "state" in query_keys:
            filters["State"] = query_keys["state"]
        if "county" in query_keys:
            filters["County"] = query_keys["county"]
        return self.data_api_url(base_url, self.DATASET_ID, filters)

    def normalize(self, api_response: Any) -> Any:
        if isinstance(api_response, dict):
            return api_response.get("data", api_response)
        return api_response
