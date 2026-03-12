"""CMS NDC — FDA NDC Directory via api.fda.gov."""

from typing import Any, Dict
from .cms_base import CMSBaseAdapter


class Adapter(CMSBaseAdapter):
    @property
    def source_name(self) -> str:
        return "cms_ndc"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        ndc = query_keys.get("ndc", "")
        return self.fda_search_url(base_url, "product_ndc", ndc)

    def normalize(self, api_response: Any) -> Any:
        if isinstance(api_response, dict):
            return api_response.get("results", api_response)
        return api_response
