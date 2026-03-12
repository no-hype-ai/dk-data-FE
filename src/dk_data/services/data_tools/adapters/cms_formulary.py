"""CMS Part D Formulary — drug coverage data via data-api."""

from typing import Any, Dict
from .cms_base import CMSBaseAdapter


class Adapter(CMSBaseAdapter):
    # Part D Formulary (Drug Coverage)
    DATASET_ID = "mgbx-jfcq"

    @property
    def source_name(self) -> str:
        return "cms_formulary"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        filters = {}
        if "ndc" in query_keys:
            filters["ndc"] = query_keys["ndc"]
        return self.data_api_url(base_url, self.DATASET_ID, filters)

    def normalize(self, api_response: Any) -> Any:
        if isinstance(api_response, dict):
            return api_response.get("data", api_response)
        return api_response
