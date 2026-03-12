"""DDInter — drug-drug interaction database via ddinter.scbdd.com API."""

from typing import Any, Dict
from urllib.parse import quote

from .cms_base import CMSBaseAdapter


class Adapter(CMSBaseAdapter):
    @property
    def source_name(self) -> str:
        return "cms_ddinter"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        drug_name = query_keys.get("drug_name", "")
        return f"{base_url}?drug={quote(drug_name)}"

    def normalize(self, api_response: Any) -> Any:
        if isinstance(api_response, dict):
            return api_response.get("data", api_response)
        return api_response
