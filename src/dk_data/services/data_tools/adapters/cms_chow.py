"""CMS CHOW — Change of Ownership records via data-api."""

from typing import Any, Dict
from .cms_base import CMSBaseAdapter


class Adapter(CMSBaseAdapter):
    # Provider Change of Ownership
    DATASET_ID = "y2hd-n93e"

    @property
    def source_name(self) -> str:
        return "cms_chow"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        filters = {}
        if "ccn" in query_keys:
            filters["CCN"] = query_keys["ccn"]
        return self.data_api_url(base_url, self.DATASET_ID, filters)

    def normalize(self, api_response: Any) -> Any:
        if isinstance(api_response, dict):
            return api_response.get("data", api_response)
        return api_response
