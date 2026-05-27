"""EMA SmPC drug label adapter — URL-only, cache-first.

Returns slim preview metadata: medicine_name, active_substance,
smpc_pdf_url. Consumers fetch the PDF themselves; this adapter never
downloads or parses the file. The mol_raw.ema_label_cache row records
which medicines have been resolved.
"""

import logging
import re
from typing import Any

import httpx

from .base import BaseAdapter

logger = logging.getLogger(__name__)

_EMA_BASE = "https://www.ema.europa.eu"
_SMP_URL_PATTERN = re.compile(r"/EPAR/([\w-]+)$", re.IGNORECASE)
_PDF_HEADERS = {"User-Agent": "dk-data-platform research@dk-data.com"}
# Source-of-truth EMA product list (mol_raw.ema) — resolves drug name to Medicine URL.
_MOLECULE_LOOKUP_SQL = """
    SELECT
        response_body->>'Medicine URL' AS medicine_url,
        response_body->>'Name of medicine' AS medicine_name,
        response_body->>'Active substance' AS active_substance
    FROM mol_raw.ema
    WHERE LOWER(response_body->>'Name of medicine') = LOWER($1)
       OR LOWER(response_body->>'Active substance') = LOWER($1)
       OR LOWER(response_body->>'International non-proprietary name (INN) / common name') = LOWER($1)
    LIMIT 1
"""
# Fast-path cache of resolved drug → SmPC PDF URL (mol_raw.ema_label_cache).
_EMA_CACHED_LABEL_LOOKUP_SQL = """
    SELECT medicine_name, active_substance, smpc_pdf_url
    FROM mol_raw.ema_label_cache
    WHERE LOWER(medicine_name) LIKE '%' || LOWER($1) || '%'
       OR LOWER(active_substance) LIKE '%' || LOWER($1) || '%'
    LIMIT 5
"""
_EMA_CACHED_LABEL_INSERT_SQL = """
    INSERT INTO mol_raw.ema_label_cache
        (medicine_name, active_substance, smpc_pdf_url, extracted_text)
    VALUES ($1, $2, $3, '{}'::jsonb)
    ON CONFLICT (smpc_pdf_url) DO UPDATE SET ingested_at = NOW()
"""


def _derive_smpc_url(medicine_url: str) -> str | None:
    """Build the English SmPC PDF URL from an EMA medicine page URL."""
    match = _SMP_URL_PATTERN.search(medicine_url)
    if not match:
        return None
    slug = match.group(1).lower()
    return f"{_EMA_BASE}/en/documents/product-information/{slug}-epar-product-information_en.pdf"


async def _verify_url(url: str) -> bool:
    """HEAD-check the derived PDF URL before caching it."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.head(url, headers=_PDF_HEADERS)
            return response.status_code == 200
    except Exception as exc:
        logger.warning("SmPC URL verify failed for %s: %s", url, exc)
        return False


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "ema_labels"

    @property
    def raw_table(self) -> str:
        return "ema_label_cache"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        return f"{_EMA_BASE}/en/medicines"

    def normalize(self, api_response: dict) -> dict:
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        """Return cached URL or derive, verify, and cache the SmPC URL."""
        async with db_pool.acquire() as conn:
            cached = await conn.fetch(_EMA_CACHED_LABEL_LOOKUP_SQL, drug_name)
            if cached:
                return {
                    "source": "ema_cache",
                    "results": [dict(row) for row in cached],
                }

            ema_row = await conn.fetchrow(_MOLECULE_LOOKUP_SQL, drug_name)
            if not ema_row or not ema_row["medicine_url"]:
                return None

            smpc_url = _derive_smpc_url(ema_row["medicine_url"])
            if not smpc_url or not await _verify_url(smpc_url):
                return None

            medicine_name = ema_row["medicine_name"] or drug_name
            active_substance = ema_row["active_substance"]
            try:
                await conn.execute(
                    _EMA_CACHED_LABEL_INSERT_SQL, medicine_name, active_substance, smpc_url
                )
            except Exception as exc:
                logger.warning("Failed to cache EMA label: %s", exc)

        return {
            "source": "ema_smpc_pdf",
            "results": [
                {
                    "medicine_name": medicine_name,
                    "active_substance": active_substance,
                    "smpc_pdf_url": smpc_url,
                }
            ],
        }
