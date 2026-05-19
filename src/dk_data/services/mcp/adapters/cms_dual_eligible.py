"""MCP Adapter: cms_dual_eligible

Feature: 019-cms-puf-platform-reconciliation
"""

from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "cms_dual_eligible"

    @property
    def raw_table(self) -> str:
        return "cms_dual_eligible"

    @property
    def raw_schema(self) -> str:
        return "hcs_raw"

    def normalize(self, api_response: dict) -> dict:
        return api_response
