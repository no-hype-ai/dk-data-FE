"""Stub adapter for CMS bulk-only sources (NPPES, POS, HCRIS, etc.).

Bulk-only sources have no external API for on-demand queries.
Data is loaded via scheduled batch jobs and queried locally.
This adapter exists so the registry can reference it without errors.
"""

from typing import Any, Dict

from .cms_base import CMSBaseAdapter


class Adapter(CMSBaseAdapter):
    """No-op adapter for bulk-only CMS sources."""

    @property
    def source_name(self) -> str:
        return "cms_bulk_stub"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        raise NotImplementedError(
            "Bulk-only source — no external API available. "
            "Data is loaded via scheduled batch jobs."
        )

    async def fetch(self, query_keys: Dict[str, str], **kwargs) -> Any:
        raise NotImplementedError(
            "Bulk-only source — no external API available."
        )

    def normalize(self, api_response: Any) -> Any:
        return api_response
