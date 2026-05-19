"""EMA SmPC drug label adapter with cache-first PDF extraction."""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .base import BaseAdapter

logger = logging.getLogger(__name__)

_EMA_BASE = "https://www.ema.europa.eu"
_SMP_URL_PATTERN = re.compile(r"/EPAR/([\w-]+)$", re.IGNORECASE)
_PDF_HEADERS = {"User-Agent": "dk-data-platform research@dk-data.com"}
_CACHE_TTL = timedelta(days=30)  # SmPC docs change slowly; re-extract after 30d
_EMA_LOOKUP_QUERY = """
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


def _is_valid_extraction(extracted: Any) -> bool:
    """An extraction is usable only if it has real text content.

    Guards against blank/zero-page/whitespace PDFs poisoning the
    UNIQUE(smpc_pdf_url) cache forever (H2).
    """
    return (
        isinstance(extracted, dict)
        and int(extracted.get("page_count") or 0) > 0
        and bool(str(extracted.get("full_text") or "").strip())
    )


def _derive_smpc_url(medicine_url: str) -> str | None:
    """Build the English SmPC PDF URL from an EMA medicine page URL."""
    match = _SMP_URL_PATTERN.search(medicine_url)
    if not match:
        return None

    slug = match.group(1).lower()
    return f"{_EMA_BASE}/en/documents/product-information/{slug}-epar-product-information_en.pdf"


def _extract_text_from_pdf(pdf_bytes: bytes) -> dict[str, Any]:
    """Extract page text and full text from a PDF payload."""
    import fitz  # pymupdf

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        pages = [page.get_text() for page in document]

    return {
        "page_count": len(pages),
        "full_text": "\n".join(pages),
        "pages": pages,
    }


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
        """Return cached label data or lazily fetch and cache SmPC text."""
        cached = await self._check_cache(drug_name, db_pool)
        if cached:
            return {"source": "ema_cache", "results": cached}

        ema_record = await self._get_ema_record(drug_name, db_pool)
        if not ema_record:
            return None

        smpc_url = _derive_smpc_url(ema_record["medicine_url"])
        if not smpc_url:
            return None

        extracted = await self._download_and_extract(smpc_url)
        if not extracted:
            return None
        if not _is_valid_extraction(extracted):
            logger.warning(
                "EMA SmPC extraction for %s was empty/garbage — not caching",
                smpc_url,
            )
            return None

        medicine_name = ema_record["medicine_name"] or drug_name
        active_substance = ema_record["active_substance"]
        await self._save_cache(
            medicine_name=medicine_name,
            active_substance=active_substance,
            smpc_url=smpc_url,
            extracted=extracted,
            db_pool=db_pool,
        )

        return {
            "source": "ema_smpc_pdf",
            "medicine_name": medicine_name,
            "smpc_pdf_url": smpc_url,
            "results": [extracted],
        }

    async def _check_cache(self, drug_name: str, db_pool: Any) -> list[dict[str, Any]] | None:
        query = """
            SELECT medicine_name, active_substance, smpc_pdf_url, extracted_text, ingested_at
            FROM mol_raw.ema_label_cache
            WHERE LOWER(medicine_name) = LOWER($1)
               OR LOWER(active_substance) = LOWER($1)
            LIMIT 5
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, drug_name)

        if not rows:
            return None

        results = []
        for row in rows:
            # TTL staleness check (enforced in Python so unit tests with fake pools work)
            ingested_at = row["ingested_at"]
            if ingested_at is not None:
                now = datetime.now(timezone.utc)
                ts = ingested_at if ingested_at.tzinfo else ingested_at.replace(tzinfo=timezone.utc)
                if now - ts > _CACHE_TTL:
                    logger.info(
                        "Stale ema_label_cache row ignored (smpc_pdf_url=%s, age>%s) — will re-extract",
                        row["smpc_pdf_url"],
                        _CACHE_TTL,
                    )
                    continue

            # H3: safe JSON decode — skip corrupt rows rather than raising 500
            extracted = row["extracted_text"]
            if isinstance(extracted, str):
                try:
                    extracted = json.loads(extracted)
                except (ValueError, TypeError) as exc:
                    logger.error(
                        "Corrupt ema_label_cache row skipped (smpc_pdf_url=%s): "
                        "extracted_text is not valid JSON: %s",
                        row["smpc_pdf_url"],
                        exc,
                    )
                    continue
            if not isinstance(extracted, dict):
                logger.error(
                    "Corrupt ema_label_cache row skipped (smpc_pdf_url=%s): "
                    "extracted_text decoded to %s, expected dict",
                    row["smpc_pdf_url"],
                    type(extracted).__name__,
                )
                continue

            results.append({
                "medicine_name": row["medicine_name"],
                "active_substance": row["active_substance"],
                "smpc_pdf_url": row["smpc_pdf_url"],
                **extracted,
            })
        return results or None  # all rows corrupt/stale → treat as cache miss

    async def _get_ema_record(self, drug_name: str, db_pool: Any) -> dict[str, Any] | None:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(_EMA_LOOKUP_QUERY, drug_name)

        if not row or not row["medicine_url"]:
            return None

        return {
            "medicine_url": row["medicine_url"],
            "medicine_name": row["medicine_name"],
            "active_substance": row["active_substance"],
        }

    async def _download_and_extract(self, smpc_url: str) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                response = await client.get(smpc_url, headers=_PDF_HEADERS)
                if response.status_code != 200:
                    logger.warning("SmPC PDF download failed: %s -> %d", smpc_url, response.status_code)
                    return None

                return _extract_text_from_pdf(response.content)
        except ImportError:
            logger.error("pymupdf not installed; cannot extract EMA SmPC PDF text")
            return None
        except Exception as exc:
            logger.warning("SmPC PDF extraction failed for %s: %s", smpc_url, exc)
            return None

    async def _save_cache(
        self,
        medicine_name: str,
        active_substance: str | None,
        smpc_url: str,
        extracted: dict[str, Any],
        db_pool: Any,
    ) -> None:
        if not _is_valid_extraction(extracted):
            logger.error(
                "Refusing to cache empty/garbage EMA extraction for %s "
                "(page_count=%r, has_text=%r)",
                smpc_url,
                extracted.get("page_count") if isinstance(extracted, dict) else None,
                bool(str((extracted or {}).get("full_text") or "").strip()) if isinstance(extracted, dict) else False,
            )
            return

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
                await conn.execute(
                    query,
                    medicine_name,
                    active_substance,
                    smpc_url,
                    json.dumps(extracted),
                )
        except Exception as exc:
            logger.warning("Failed to cache EMA label: %s", exc)
