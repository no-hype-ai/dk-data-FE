"""MCP Adapter: cms_geographic_variation

Feature: 019-cms-puf-platform-reconciliation
"""

from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "cms_geographic_variation"

    @property
    def raw_table(self) -> str:
        return "cms_geographic_variation"

    @property
    def raw_schema(self) -> str:
        return "hcs_raw"

    def normalize(self, api_response: dict) -> dict:
        return api_response
