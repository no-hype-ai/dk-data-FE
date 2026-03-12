"""Base CMS adapter for queryable CMS data sources.

Provides shared logic for CMS DKAN/data-api query building, httpx-based
async fetching, and response normalization. Individual CMS adapters
subclass this and override dataset_id / query_builder as needed.

CMS APIs used:
- data.cms.gov DKAN SQL: /api/1/datastore/sql?query=SELECT ...
- data.cms.gov data-api: /data-api/v1/dataset/{uuid}/data
- openpaymentsdata.cms.gov: /api/1/datastore/sql?query=SELECT ...
- api.fda.gov: /drug/ndc.json?search=...
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from loguru import logger

# Strict pattern for values interpolated into DKAN SQL strings.
# Only allows alphanumeric, spaces, hyphens, and dots — rejects quotes, semicolons, etc.
_SAFE_SQL_VALUE = re.compile(r"^[a-zA-Z0-9 .\-]+$")


class CMSBaseAdapter(ABC):
    """Base adapter for CMS queryable data sources.

    Subclasses must implement:
    - source_name: identifier for this source
    - build_query_url(query_keys): construct the full API URL
    - normalize(api_response): normalize to canonical format
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Identifier for this data source."""
        ...

    @abstractmethod
    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        """Build the API URL from query parameters.

        Args:
            base_url: The tool's api_base_url.
            query_keys: Validated query parameters (e.g., {"npi": "123"}).

        Returns:
            Full URL with query parameters.
        """
        ...

    def normalize(self, api_response: Any) -> Any:
        """Normalize API response. Default passes through."""
        if isinstance(api_response, dict):
            # Common CMS DKAN pattern: results in a list
            return api_response.get("results", api_response)
        return api_response

    async def fetch(
        self,
        query_keys: Dict[str, str],
        timeout: float = 30.0,
        base_url: Optional[str] = None,
    ) -> Any:
        """Fetch data from the external CMS API.

        Args:
            query_keys: Query parameters to pass to the API.
            timeout: Request timeout in seconds.
            base_url: Override base URL (defaults to tool definition's url).

        Returns:
            Parsed JSON response.
        """
        url = self.build_query_url(base_url or "", query_keys)

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    # ── Helper methods for common CMS URL patterns ──

    @staticmethod
    def _escape_sql_value(value: str) -> str:
        """Validate and escape a value for DKAN SQL string interpolation.

        Raises ValueError if the value contains unsafe characters.
        """
        if not _SAFE_SQL_VALUE.match(value):
            raise ValueError(f"Unsafe value for DKAN SQL: {value!r}")
        return value

    @staticmethod
    def dkan_sql_url(base_url: str, sql: str) -> str:
        """Build a CMS DKAN SQL endpoint URL.

        Example: https://data.cms.gov/provider-data/api/1/datastore/sql?query=SELECT ...
        """
        return f"{base_url}?query={quote(sql)}"

    @staticmethod
    def data_api_url(base_url: str, dataset_id: str, filters: Dict[str, str], limit: int = 100) -> str:
        """Build a CMS data-api v1 URL with filters.

        Example: https://data.cms.gov/data-api/v1/dataset/{uuid}/data?filter[npi]=123&size=100
        """
        params = "&".join(f"filter[{k}]={quote(str(v))}" for k, v in filters.items())
        return f"{base_url}/{dataset_id}/data?{params}&size={limit}"

    @staticmethod
    def fda_search_url(base_url: str, field: str, value: str, limit: int = 100) -> str:
        """Build an FDA API search URL.

        Example: https://api.fda.gov/drug/ndc.json?search=product_ndc:"xxx"&limit=100
        """
        return f'{base_url}?search={field}:"{quote(value)}"&limit={limit}'


class Adapter(CMSBaseAdapter):
    """Default stub — should not be instantiated directly.

    Individual CMS source modules override this class.
    """

    @property
    def source_name(self) -> str:
        return "cms_base"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        raise NotImplementedError("Use a specific CMS adapter, not the base class")
