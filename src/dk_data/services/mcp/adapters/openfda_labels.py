"""OpenFDA drug label adapter — DB-first lookup with API fallback.

Returns slim preview metadata: brand_name, generic_name, pdf_url
(DailyMed SPL PDF), and boxed_warning. Full label text lives in the PDF.
"""

import json
import logging
from typing import Any
from urllib.parse import quote

import httpx

from .base import BaseAdapter

logger = logging.getLogger(__name__)

_FDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
_DAILYMED_PDF_URL = "https://dailymed.nlm.nih.gov/dailymed/downloadpdffile.cfm?setId="
_DB_LOOKUP_QUERY = """
    SELECT label
    FROM mol_raw.openfda_labels,
         LATERAL jsonb_array_elements(response_body->'results') AS label
    WHERE LOWER(label->'openfda'->>'generic_name') LIKE '%' || LOWER($1) || '%'
       OR LOWER(label->'openfda'->>'brand_name') LIKE '%' || LOWER($1) || '%'
    LIMIT 5
"""


def _first(value: Any) -> str | None:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _to_preview(label: Any) -> dict[str, Any] | None:
    """Project a raw OpenFDA label dict to slim preview fields."""
    if isinstance(label, str):
        try:
            label = json.loads(label)
        except json.JSONDecodeError:
            return None
    if not isinstance(label, dict):
        return None

    openfda = label.get("openfda") or {}
    set_id = _first(openfda.get("spl_set_id")) or label.get("set_id")
    return {
        "brand_name": _first(openfda.get("brand_name")),
        "generic_name": _first(openfda.get("generic_name")),
        "pdf_url": f"{_DAILYMED_PDF_URL}{set_id}" if set_id else None,
        "boxed_warning": _first(label.get("boxed_warning")),
    }


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
        encoded = quote(f'openfda.generic_name:"{drug_name}"')
        return f"{_FDA_LABEL_URL}?search={encoded}&limit=5"

    def normalize(self, api_response: dict) -> dict:
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        """Local DB lookup; fall back to OpenFDA API if no local match."""
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(_DB_LOOKUP_QUERY, drug_name)
            previews = [p for row in rows if (p := _to_preview(row["label"]))]
            if previews:
                return {"source": "openfda_local", "results": previews}
        except Exception as exc:
            logger.warning("FDA local DB lookup failed: %s", exc)

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(self.build_url(_FDA_LABEL_URL, drug_name, {}))
        except Exception as exc:
            logger.warning("FDA label API lookup failed: %s", exc)
            return None
        if response.status_code != 200:
            return None

        results = response.json().get("results") or []
        previews = [p for label in results if (p := _to_preview(label))]
        return {"source": "openfda", "results": previews} if previews else None
