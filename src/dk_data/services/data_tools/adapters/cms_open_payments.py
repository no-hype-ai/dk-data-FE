"""CMS Open Payments — physician/industry financial relationships via DKAN SQL.

Queries all 3 payment types: general, research, and ownership.
Raw tables: cms_open_payments_general, cms_open_payments_research, cms_open_payments_ownership.
"""

from typing import Any, Dict, List
from .cms_base import CMSBaseAdapter


# CMS Open Payments has 3 separate DKAN datasets
_PAYMENT_DATASETS = {
    "general":   "gvhb-bfwy",
    "research":  "8bes-6cbr",
    "ownership": "gydn-aebz",
}


class Adapter(CMSBaseAdapter):
    # Default: general payments (backward compat for single-query callers)
    DATASET_SQL_TABLE = "gvhb-bfwy"

    @property
    def source_name(self) -> str:
        return "cms_open_payments"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        """Build URL for the general payments dataset.

        For multi-dataset queries, use build_all_query_urls() instead.
        """
        conditions = []
        if "npi" in query_keys:
            conditions.append(f"covered_recipient_npi = '{self._escape_sql_value(query_keys['npi'])}'")
        if "state" in query_keys:
            conditions.append(f"recipient_state = '{self._escape_sql_value(query_keys['state'])}'")
        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"[SELECT * FROM {self.DATASET_SQL_TABLE}][WHERE {where}][LIMIT 100]"
        return self.dkan_sql_url(base_url, sql)

    def build_all_query_urls(self, base_url: str, query_keys: Dict[str, str]) -> Dict[str, str]:
        """Build URLs for all 3 payment datasets (general, research, ownership).

        Returns:
            Dict mapping payment_type → full URL.
        """
        urls = {}
        for payment_type, dataset_id in _PAYMENT_DATASETS.items():
            conditions = []
            if "npi" in query_keys:
                conditions.append(f"covered_recipient_npi = '{self._escape_sql_value(query_keys['npi'])}'")
            if "state" in query_keys:
                conditions.append(f"recipient_state = '{self._escape_sql_value(query_keys['state'])}'")
            where = " AND ".join(conditions) if conditions else "1=1"
            sql = f"[SELECT * FROM {dataset_id}][WHERE {where}][LIMIT 100]"
            urls[payment_type] = self.dkan_sql_url(base_url, sql)
        return urls

    async def fetch(
        self,
        query_keys: Dict[str, str],
        timeout: float = 30.0,
        base_url: str | None = None,
    ) -> Any:
        """Fetch from all 3 Open Payments datasets and merge results.

        Returns combined list with a `payment_type` field added to each record.
        """
        import httpx

        urls = self.build_all_query_urls(base_url or "", query_keys)
        combined: List[Dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=timeout) as client:
            for payment_type, url in urls.items():
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    data = response.json()
                    records = self.normalize(data)
                    if isinstance(records, list):
                        for r in records:
                            if isinstance(r, dict):
                                r["payment_type"] = payment_type
                            combined.append(r)
                    elif isinstance(records, dict):
                        records["payment_type"] = payment_type
                        combined.append(records)
                except httpx.HTTPStatusError:
                    # Some payment types may not have data — skip gracefully
                    pass

        return combined

    def normalize(self, api_response: Any) -> Any:
        return api_response
