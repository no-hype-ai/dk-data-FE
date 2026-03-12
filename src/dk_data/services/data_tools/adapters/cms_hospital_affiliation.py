"""CMS Hospital-Physician Affiliations via DKAN SQL."""

from typing import Any, Dict
from .cms_base import CMSBaseAdapter


class Adapter(CMSBaseAdapter):
    # Physician Compare National - Physician Hospital Affiliations
    DATASET_SQL_TABLE = "2cxb-azmn"

    @property
    def source_name(self) -> str:
        return "cms_hospital_affiliation"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        conditions = []
        if "ccn" in query_keys:
            conditions.append(f"hospital_ccn = '{self._escape_sql_value(query_keys['ccn'])}'")
        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"[SELECT * FROM {self.DATASET_SQL_TABLE}][WHERE {where}][LIMIT 100]"
        return self.dkan_sql_url(base_url, sql)

    def normalize(self, api_response: Any) -> Any:
        return api_response
