"""MCP Adapter: cms_cost_reports

Feature: 015-assessment-dashboard-integration
"""

from .base import BaseAdapter


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "cms_cost_reports"

    @property
    def raw_table(self) -> str:
        return "cms_cost_reports"

    @property
    def raw_schema(self) -> str:
        return "raw"

    def normalize(self, api_response: dict) -> dict:
        return api_response
