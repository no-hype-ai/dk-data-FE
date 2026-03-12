"""CMS Hospital Quality — star ratings and measures via DKAN SQL."""

from typing import Any, Dict
from .cms_base import CMSBaseAdapter


class Adapter(CMSBaseAdapter):
    # Hospital General Information (includes star ratings)
    DATASET_SQL_TABLE = "xubh-q36u"

    @property
    def source_name(self) -> str:
        return "cms_hospital_quality"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        conditions = []
        if "ccn" in query_keys:
            conditions.append(f"facility_id = '{self._escape_sql_value(query_keys['ccn'])}'")
        if "state" in query_keys:
            conditions.append(f"state = '{self._escape_sql_value(query_keys['state'])}'")
        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"[SELECT * FROM {self.DATASET_SQL_TABLE}][WHERE {where}][LIMIT 100]"
        return self.dkan_sql_url(base_url, sql)

    def normalize(self, api_response: Any) -> Any:
        return api_response
