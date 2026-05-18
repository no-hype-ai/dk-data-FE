"""Unified drug label search adapter — FDA text labels + EMA SmPC (lazy PDF extraction).

FDA path: queries OpenFDA /drug/label.json API directly (returns text).
EMA path: checks mol_raw.ema_label_cache → on miss, derives SmPC PDF URL
from mol_raw.ema Medicine URL, downloads PDF, extracts text via pymupdf,
caches in DB, returns.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from .base import BaseAdapter

logger = logging.getLogger(__name__)

_FDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
_EMA_BASE = "https://www.ema.europa.eu"


def _derive_smpc_url(medicine_url: str) -> Optional[str]:
    """Derive English SmPC PDF URL from EMA product page URL.

    Pattern: /en/medicines/human/EPAR/{slug}
         ->  /en/documents/product-information/{slug}-epar-product-information_en.pdf
    """
    match = re.search(r"/EPAR/([\w-]+)$", medicine_url, re.I)
    if not match:
        return None
    slug = match.group(1).lower()
    return f"{_EMA_BASE}/en/documents/product-information/{slug}-epar-product-information_en.pdf"


def _extract_text_from_pdf(pdf_bytes: bytes) -> Dict[str, Any]:
    """Extract text from PDF bytes using pymupdf. Returns sectioned text."""
    import fitz  # pymupdf

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    full_text = []
    for page in doc:
        text = page.get_text()
        pages.append(text)
        full_text.append(text)
    doc.close()

    combined = "\n".join(full_text)
    return {
        "page_count": len(pages),
        "full_text": combined,
        "pages": pages,
    }


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "drug_labels"

    @property
    def raw_table(self) -> str:
        return "ema_label_cache"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        return f'{_FDA_LABEL_URL}?search=openfda.generic_name:"{quote(drug_name)}"&limit=5'

    def normalize(self, api_response: dict) -> dict:
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> Optional[dict]:
        """Unified label lookup: FDA from API, EMA from cache or lazy extraction."""
        fda_data = await self._fda_lookup(drug_name)
        ema_data = await self._ema_lookup(drug_name, db_pool)

        if not fda_data and not ema_data:
            return None

        return {
            "drug_name": drug_name,
            "fda": fda_data,
            "ema": ema_data,
        }

    async def _fda_lookup(self, drug_name: str) -> Optional[dict]:
        """Fetch FDA label text from OpenFDA API."""
        url = f'{_FDA_LABEL_URL}?search=openfda.generic_name:"{quote(drug_name)}"&limit=5'
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                if not data.get("results"):
                    return None
                return {"source": "openfda", "results": data["results"]}
        except Exception as exc:
            logger.warning("FDA label lookup failed: %s", exc)
            return None

    async def _ema_lookup(self, drug_name: str, db_pool: Any) -> Optional[dict]:
        """Check EMA label cache, lazy-extract on miss."""
        cached = await self._check_cache(drug_name, db_pool)
        if cached:
            return {"source": "ema_cache", "results": cached}

        smpc_url = await self._find_smpc_url(drug_name, db_pool)
        if not smpc_url:
            return None

        extracted = await self._download_and_extract(smpc_url)
        if not extracted:
            return None

        medicine_name, active_substance = await self._get_ema_names(drug_name, db_pool)
        await self._save_cache(medicine_name or drug_name, active_substance, smpc_url, extracted, db_pool)

        return {
            "source": "ema_smpc_pdf",
            "medicine_name": medicine_name,
            "smpc_pdf_url": smpc_url,
            "results": [extracted],
        }

    async def _check_cache(self, drug_name: str, db_pool: Any) -> Optional[List[dict]]:
        query = """
            SELECT medicine_name, active_substance, smpc_pdf_url, extracted_text
            FROM mol_raw.ema_label_cache
            WHERE LOWER(medicine_name) = LOWER($1)
               OR LOWER(active_substance) = LOWER($1)
            LIMIT 5
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, drug_name)
        if not rows:
            return None
        return [
            {
                "medicine_name": r["medicine_name"],
                "active_substance": r["active_substance"],
                "smpc_pdf_url": r["smpc_pdf_url"],
                **r["extracted_text"],
            }
            for r in rows
        ]

    async def _find_smpc_url(self, drug_name: str, db_pool: Any) -> Optional[str]:
        """Find SmPC PDF URL by looking up Medicine URL in mol_raw.ema."""
        query = """
            SELECT response_body->>'Medicine URL' as medicine_url,
                   response_body->>'Name of medicine' as name
            FROM mol_raw.ema
            WHERE LOWER(response_body->>'Name of medicine') = LOWER($1)
               OR LOWER(response_body->>'Active substance') = LOWER($1)
               OR LOWER(response_body->>'International non-proprietary name (INN) / common name') = LOWER($1)
            LIMIT 1
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, drug_name)
        if not row or not row["medicine_url"]:
            return None
        return _derive_smpc_url(row["medicine_url"])

    async def _get_ema_names(self, drug_name: str, db_pool: Any) -> tuple:
        query = """
            SELECT response_body->>'Name of medicine' as name,
                   response_body->>'Active substance' as substance
            FROM mol_raw.ema
            WHERE LOWER(response_body->>'Name of medicine') = LOWER($1)
               OR LOWER(response_body->>'Active substance') = LOWER($1)
               OR LOWER(response_body->>'International non-proprietary name (INN) / common name') = LOWER($1)
            LIMIT 1
        """
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, drug_name)
        if not row:
            return (drug_name, None)
        return (row["name"], row["substance"])

    async def _download_and_extract(self, smpc_url: str) -> Optional[dict]:
        """Download SmPC PDF and extract text."""
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                resp = await client.get(
                    smpc_url,
                    headers={"User-Agent": "dk-data-platform research@dk-data.com"},
                )
                if resp.status_code != 200:
                    logger.warning("SmPC PDF download failed: %s → %d", smpc_url, resp.status_code)
                    return None
                return _extract_text_from_pdf(resp.content)
        except ImportError:
            logger.error("pymupdf not installed — cannot extract EMA SmPC PDF text")
            return None
        except Exception as exc:
            logger.warning("SmPC PDF extraction failed for %s: %s", smpc_url, exc)
            return None

    async def _save_cache(
        self, medicine_name: str, active_substance: Optional[str],
        smpc_url: str, extracted: dict, db_pool: Any,
    ) -> None:
        import json
        query = """
            INSERT INTO mol_raw.ema_label_cache
                (medicine_name, active_substance, smpc_pdf_url, extracted_text)
            VALUES ($1, $2, $3, $4::jsonb)
            ON CONFLICT (smpc_pdf_url) DO UPDATE SET
                extracted_text = EXCLUDED.extracted_text,
                ingested_at = NOW()
        """
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(query, medicine_name, active_substance, smpc_url, json.dumps(extracted))
        except Exception as exc:
            logger.warning("Failed to cache EMA label: %s", exc)
