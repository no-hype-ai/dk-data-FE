"""MCP Adapter: openfda_labels
Feature: 015-assessment-dashboard-integration
"""
import logging
from typing import Any
from urllib.parse import quote

import httpx

from .base import BaseAdapter

logger = logging.getLogger(__name__)

_FDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
_RESULT_LIMIT = 5
_HTTP_TIMEOUT_SECONDS = 30
_DB_LOOKUP_QUERY = """
    SELECT response_body->'results'->0 AS label_data
    FROM mol_raw.openfda_labels
    WHERE LOWER(response_body->'results'->0->'openfda'->>'generic_name') LIKE '%' || LOWER($1) || '%'
       OR LOWER(response_body->'results'->0->'openfda'->>'brand_name') LIKE '%' || LOWER($1) || '%'
    LIMIT 5
"""


def _build_openfda_url(drug_name: str) -> str:
    """Build a generic-name OpenFDA label search URL."""
    encoded_query = quote(f'openfda.generic_name:"{drug_name}"')
    return f"{_FDA_LABEL_URL}?search={encoded_query}&limit={_RESULT_LIMIT}"


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "openfda_labels"

    @property
    def raw_table(self) -> str:
        return "openfda_labels"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """OpenFDA drug/label uses search parameter with openfda field queries."""
        return f'{base_url}?search=openfda.generic_name:"{quote(drug_name)}"&limit=5'

    def normalize(self, api_response: dict) -> dict:
        """Normalize OpenFDA drug/label response."""
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        """Return local label data first, then fall back to OpenFDA."""
        local_result = await self._db_lookup(drug_name, db_pool)
        if local_result:
            return local_result

        return await self._api_lookup(drug_name)

    async def _db_lookup(self, drug_name: str, db_pool: Any) -> dict[str, Any] | None:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(_DB_LOOKUP_QUERY, drug_name)
        results = [row["label_data"] for row in rows if row["label_data"]]
        if not results:
            return None
        return {"source": "openfda_local", "results": results}

    async def _api_lookup(self, drug_name: str) -> dict[str, Any] | None:
        url = _build_openfda_url(drug_name)
        try:
            async with httpx.AsyncClient(
                timeout=_HTTP_TIMEOUT_SECONDS,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
        except Exception as exc:
            logger.warning("FDA label API lookup failed: %s", exc)
            return None

        if response.status_code != 200:
            return None

        data = response.json()
        results = data.get("results")
        if not results:
            return None

        return {"source": "openfda", "results": results}
